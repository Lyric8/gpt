from __future__ import annotations

import argparse
import fcntl
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .artifacts import Artifacts, digest
from .governor import IntegrityError
from .queue import EventQueue


class ProtocolDrift(IntegrityError):
    pass


def _git(bare: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "--git-dir=" + str(bare), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("git observation failed: " + result.stderr[:1024].decode(errors="replace"))
    if len(result.stdout) > 32 * 1024 * 1024:
        raise RuntimeError("git observation output exceeds 32 MiB; no source state was advanced")
    return result.stdout


def _reconcile_source_set(queue: EventQueue, channel: str,
                          events: Iterable[dict[str, Any]]) -> int:
    """Insert immutable source identities without using branch HEAD as a cursor.

    The identity is exactly (channel, source_path, source_blob_sha). A branch
    commit is only a read snapshot used to enumerate the current tree; it is
    never compared with a previous commit to decide whether an event exists.
    """
    prepared: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for event in events:
        key = event.get("key")
        version = event.get("version")
        if not isinstance(key, str) or not key:
            raise ValueError("event source path is required")
        if not isinstance(version, str) or not version:
            raise ValueError("event source blob sha is required")
        ref = queue.store.put_json(event)
        prepared.append((digest([channel, key, version]), event, ref))

    inserted = 0
    with queue.tx() as c:
        for event_id, event, ref in prepared:
            row = c.execute("SELECT payload_sha FROM events WHERE id=?", (event_id,)).fetchone()
            if row is not None and row["payload_sha"] != ref["sha256"]:
                raise IntegrityError("same source identity resolved to different event payload")
            inserted += c.execute(
                """INSERT OR IGNORE INTO events
                   (id,channel,item_key,version,payload_sha,state,available)
                   VALUES(?,?,?,?,?,'PENDING',?)""",
                (event_id, channel, event["key"], event["version"], ref["sha256"], queue.clock()),
            ).rowcount
    return inserted


def _due_count(queue: EventQueue, channel: str) -> int:
    now = queue.clock()
    with queue.tx() as c:
        row = c.execute(
            """SELECT COUNT(*) AS n FROM events
               WHERE channel=? AND available<=? AND
                     (state='PENDING' OR (state='RUNNING' AND expires<=?))""",
            (channel, now, now),
        ).fetchone()
        return int(row["n"])


def scan_git_inbox(bare: Path, queue: EventQueue, *, expected_protocol: dict[str, str],
                   inbox: str = "chat/to-hermes/") -> dict[str, Any]:
    """Zero-model source scan with fail-closed observation semantics.

    Success/no-event is based on the absence of unseen (path, blob) identities
    after a complete scan plus the absence of due local retries. Git HEAD is not
    an event identity and is not used as an unchanged fast path.
    """
    if not expected_protocol:
        raise IntegrityError("approved protocol blob hashes are required")
    if not inbox.startswith("chat/") or not inbox.endswith("/"):
        raise ValueError("inbox must be an explicit chat/.../ prefix")

    bare = bare.resolve(strict=True)
    channel = "github:Lyric8/gpt:chat:" + inbox.strip("/").split("/")[-1]
    with (bare / "stage1-source-scan.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _git(
            bare,
            "fetch",
            "--no-tags",
            "--depth=1",
            "origin",
            "+refs/heads/chat:refs/remotes/origin/chat",
        )
        snapshot = _git(bare, "rev-parse", "refs/remotes/origin/chat").decode().strip()

        allowed_protocol = {
            "chat/README.md",
            "chat/LEASE_PROTOCOL.md",
            "chat/RESOURCE_LEASE_PROTOCOL.md",
        }
        for path, expected in expected_protocol.items():
            if path not in allowed_protocol:
                raise ProtocolDrift("unexpected protocol path in approval snapshot: " + path)
            actual = _git(bare, "rev-parse", snapshot + ":" + path).decode().strip()
            if actual != expected:
                raise ProtocolDrift("protocol changed; review before scanner activation: " + path)

        records = _git(bare, "ls-tree", "-rz", snapshot, "--", inbox).split(b"\0")
        events: list[dict[str, Any]] = []
        for record in records:
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, sha = meta.decode("ascii").split()
            path = raw_path.decode("utf-8")
            if kind != "blob" or not path.endswith(".md"):
                continue
            if mode not in ("100644", "100755"):
                raise IntegrityError("non-regular relay source refused: " + path)
            content = _git(bare, "cat-file", "blob", sha)
            source_ref = queue.store.put(content)
            events.append(
                {
                    "key": path,
                    "version": sha,
                    "kind": "relay.reconcile",
                    "source_artifact": source_ref,
                    "required_checks": [
                        "message_lease",
                        "resource_lease_or_not_required",
                        "business_verification",
                        "remote_receipt_readback",
                        "remote_completion_readback",
                    ],
                }
            )

        inserted = _reconcile_source_set(queue, channel, events)
        due = _due_count(queue, channel)
        return {
            "status": "NEW_SOURCE" if inserted else ("PENDING" if due else "NO_NEW_SOURCE"),
            "queued": inserted,
            "due": due,
            "source_count": len(events),
            "provider_calls": 0,
            "dispatch_required": due > 0,
            "snapshot_commit": snapshot,
            "identity_rule": "source_path+source_blob_sha",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage1 zero-model Git source scanner")
    parser.add_argument("--bare", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--inbox", default="chat/to-hermes/")
    args = parser.parse_args()

    state = Path(args.state)
    queue = EventQueue(state / "events.sqlite3", Artifacts(state / "artifacts"))
    try:
        result = scan_git_inbox(
            Path(args.bare),
            queue,
            expected_protocol=json.loads(Path(args.protocol).read_text()),
            inbox=args.inbox,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 10 if result["dispatch_required"] else 0
    except ProtocolDrift as exc:
        print(json.dumps({"status": "PROTOCOL_DRIFT", "error": str(exc), "provider_calls": 0}, ensure_ascii=False))
        return 21
    except (OSError, RuntimeError, sqlite3.Error, IntegrityError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc), "provider_calls": 0}, ensure_ascii=False))
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
