from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
from pathlib import Path
from typing import Any

from .artifacts import Artifacts
from .governor import IntegrityError
from .queue import EventQueue


def git(bare: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "--git-dir=" + str(bare), *args], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=90, check=False)
    if result.returncode:
        raise RuntimeError("git observation failed: " + result.stderr[:1024].decode(errors="replace"))
    if len(result.stdout) > 16 * 1024 * 1024:
        raise RuntimeError("Git output exceeds observer limit; no cursor advanced")
    return result.stdout


def observe(bare: Path, queue: EventQueue, *, expected_protocol: dict[str, str]) -> dict[str, Any]:
    """Read blobs from a bare Git cache: no checkout, no filename-length recursion.

    On bootstrap ALL sources are enqueued for deterministic reconciliation with
    remote completion markers. No unreviewed historical watermark is invented.
    Source events do NOT include mutable branch HEAD, so self-writes cannot change
    their identities. A separate deterministic dispatcher drains existing pending
    work even when HEAD is unchanged. This observer never starts an LLM.
    """
    if not expected_protocol:
        raise IntegrityError("approved protocol blob hashes are required")
    bare = bare.resolve(strict=True)
    with (bare / "token-observer.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        git(bare, "fetch", "--no-tags", "--depth=1", "origin",
            "+refs/heads/chat:refs/remotes/origin/chat")
        head = git(bare, "rev-parse", "refs/remotes/origin/chat").decode().strip()
        for path, expected in expected_protocol.items():
            if path not in ("chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md"):
                raise IntegrityError("unexpected protocol path")
            actual = git(bare, "rev-parse", head + ":" + path).decode().strip()
            if actual != expected:
                raise IntegrityError("protocol changed; review before activating scanner: " + path)
        channel = "github:Lyric8/gpt:chat:to-hermes"
        old = queue.cursor(channel)
        if head == old:
            return {"wakeAgent": False, "queued": 0, "status": "UNCHANGED", "head": head}
        records = git(bare, "ls-tree", "-rz", head, "--", "chat/to-hermes/").split(b"\0")
        events = []
        for record in records:
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, kind, sha = meta.decode("ascii").split()
            path = raw_path.decode("utf-8")
            if kind != "blob" or not path.endswith(".md"):
                continue
            if mode not in ("100644", "100755"):
                raise IntegrityError("non-regular relay file refused")
            content = git(bare, "cat-file", "blob", sha)
            ref = queue.store.put(content)
            events.append({"key": path, "version": sha, "kind": "relay.reconcile",
                           "source_artifact": ref, "required_checks": ["message_lease",
                           "resource_lease_or_not_required", "business_verification",
                           "remote_receipt_readback", "remote_completion_readback"]})
        count = queue.ingest(channel, old, head, events)
        return {"wakeAgent": False, "queued": count, "status": "SCANNED", "head": head,
                "requires": "deterministic dispatcher; do not interpret queued count as permission to wake an agent"}


def main() -> int:
    p = argparse.ArgumentParser(description="Zero-LLM Git inbox observer (local staging only)")
    p.add_argument("--bare", required=True); p.add_argument("--state", required=True)
    p.add_argument("--protocol", required=True)
    args = p.parse_args()
    state = Path(args.state)
    queue = EventQueue(state / "events.sqlite3", Artifacts(state / "artifacts"))
    try:
        result = observe(Path(args.bare), queue, expected_protocol=json.loads(Path(args.protocol).read_text()))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc), "wakeAgent": False}, ensure_ascii=False))
        return 1  # A failed watchdog must be visible; do not advance the cursor.


if __name__ == "__main__":
    raise SystemExit(main())
