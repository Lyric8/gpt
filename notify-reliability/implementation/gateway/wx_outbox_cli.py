"""Credential-free producers/health/migration. Run with Hermes' Python environment.

Exit 0 means this CLI operation succeeded; inspect delivery_state to distinguish
local admission from a provider ACK. No command here sends network requests.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

from gateway.reliable_outbox import Store, canonical, digest


def admit(s: Store, *, account: str, profile: str, chat: str, key: str, body: str) -> dict:
    mid = s.reserve(account=account, profile=profile, chat=chat, key=key,
                    raw={"type": "text", "body": body}, session=None,
                    ready=True, category="notification")
    status = s.status(mid)
    return {"operation": "admit", "id": mid, "durable": True,
            "provider_accepted": status["state"] == "accepted", "delivery_state": status["state"]}


def legacy_candidates(s: Store, profile: str) -> list[dict]:
    with s.connect() as c:
        return [dict(r) for r in c.execute("""SELECT obligation_id,state,attempts,length(content) AS characters,created_at
            FROM delivery_obligations WHERE platform='weixin' AND COALESCE(adapter_profile,'default')=?
              AND state IN ('pending','attempting','failed') ORDER BY created_at""", (profile,))]


def import_queue(s: Store, directory: Path, *, account: str, profile: str, chat: str,
                 accept_partial_duplicates: bool = False) -> list[dict]:
    """Non-destructive ownership transfer after stopping the old shell sender.

    .part is not a reliable provider receipt. A nonzero/malformed progress file
    is refused unless the operator explicitly accepts a full, labelled replay.
    Files are NEVER deleted here, regardless of admission or ACK state.
    """
    import re
    results = []
    for path in sorted(directory.glob("*.txt")):
        if not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]+\.txt", path.name) or path.with_name(path.name+".done").exists():
            continue
        progress = path.with_name(path.name+".part")
        ambiguous = False
        if progress.exists():
            try:
                ambiguous = int(progress.read_text().strip() or "0") != 0
            except ValueError:
                ambiguous = True
        if ambiguous and not accept_partial_duplicates:
            results.append({"source": path.name, "state": "manual_partial_replay_required"})
            continue
        body = path.read_text(encoding="utf-8")
        # Filename identifies an event. Body is checked for consistency by Store;
        # identical body in a different event is NOT globally deduplicated.
        key = "legacy-queue:" + digest(str(path.resolve()))
        body = "【旧队列迁移，历史发送结果可能不确定】\n" + body
        result = admit(s, account=account, profile=profile, chat=chat, key=key, body=body)
        results.append({"source": path.name, **result})
    return results


def collect_cron(s: Store, root: Path, *, account: str, profile: str, chat: str,
                 since_epoch: float) -> list[dict]:
    """Scan every immutable output file since an explicit activation watermark.

    Never infer ACKs from logs and never only inspect the latest file per job.
    Do not mutate source files; repeated collection is safe via event identity.
    """
    import re
    results = []
    for path in sorted(root.glob("*/*.md")):
        st = path.stat()
        if st.st_mtime < since_epoch or time.time() - st.st_mtime < 10:
            continue
        text = path.read_text(encoding="utf-8")
        marks = list(re.finditer(r"(?m)^##\s*Response\s*$", text))
        if not marks:
            continue
        body = text[marks[-1].end():].strip()
        if not body or (body.startswith("[SILENT]") and len(body) < 40):
            continue
        # Immutable output path = event; edits are explicit conflicts, not new notifications.
        key = "cron-output:"+digest(str(path.resolve()))
        results.append(admit(s, account=account, profile=profile, chat=chat, key=key, body=body))
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--account", required=True)
    p.add_argument("--profile", default="default")
    sub = p.add_subparsers(dest="command", required=True)
    q = sub.add_parser("enqueue")
    q.add_argument("--chat", required=True)
    q.add_argument("--key", required=True)
    q.add_argument("--file", type=Path, required=True)
    q = sub.add_parser("status"); q.add_argument("id")
    sub.add_parser("health")
    sub.add_parser("watchdog")
    sub.add_parser("resume")
    sub.add_parser("scrub-accepted")
    sub.add_parser("legacy-list")
    q = sub.add_parser("legacy-import")
    q.add_argument("--id", action="append", required=True)
    q.add_argument("--apply", action="store_true")
    q.add_argument("--writers-stopped", action="store_true")
    q = sub.add_parser("queue-import")
    q.add_argument("--directory", type=Path, required=True)
    q.add_argument("--chat", required=True)
    q.add_argument("--writers-stopped", action="store_true")
    q.add_argument("--accept-partial-duplicates", action="store_true")
    q = sub.add_parser("collect-cron")
    q.add_argument("--directory", type=Path, required=True)
    q.add_argument("--chat", required=True)
    q.add_argument("--since-epoch", type=float, required=True)
    a = p.parse_args()
    # Health must not create an empty DB and accidentally make a dead install look healthy.
    if a.command in {"health", "watchdog", "status"} and not a.db.exists():
        print(canonical({"healthy": False, "error": "database_missing"}))
        return 2
    s = Store(a.db)
    if a.command == "enqueue":
        result = admit(s, account=a.account, profile=a.profile, chat=a.chat,
                       key=a.key, body=a.file.read_text(encoding="utf-8"))
    elif a.command == "status":
        result = s.status(a.id)
    elif a.command in {"health", "watchdog"}:
        result = s.health(a.account)
        hb = result["heartbeat_age_seconds"]
        result["healthy"] = hb is not None and hb < 30 and not result["paused"] and not result["counts"].get("blocked") and result["oldest_pending_seconds"] < 120 and not result["clock_anomaly"] and result["disk_free_bytes"] >= 512 * 1024 * 1024
        print(canonical(result))
        return 0 if result["healthy"] else 2
    elif a.command == "resume":
        s.resume(a.account)
        result = {"operation": "resume", "provider_accepted": False}
    elif a.command == "scrub-accepted":
        result = {"scrubbed": s.scrub_accepted_payloads()}
    elif a.command == "legacy-list":
        result = legacy_candidates(s, a.profile)
    elif a.command == "legacy-import":
        if a.apply and not a.writers_stopped:
            p.error("--apply requires --writers-stopped; stop/verify both old gateway and sender first")
        result = s.import_legacy(a.account, a.profile, a.id, apply=a.apply)
    elif a.command == "queue-import":
        if not a.writers_stopped:
            p.error("queue-import requires --writers-stopped")
        result = import_queue(s, a.directory, account=a.account, profile=a.profile, chat=a.chat,
                              accept_partial_duplicates=a.accept_partial_duplicates)
    else:
        result = collect_cron(s, a.directory, account=a.account, profile=a.profile, chat=a.chat,
                              since_epoch=a.since_epoch)
    print(canonical(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, sqlite3.Error, ValueError, RuntimeError, KeyError) as exc:
        # Do not print DB content, local paths, raw HTTP responses or credentials.
        print(canonical({"operation_failed": True, "exception_type": type(exc).__name__}), file=sys.stderr)
        sys.exit(2)
