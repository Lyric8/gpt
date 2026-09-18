from __future__ import annotations

import fcntl
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .storage import Journal, best_effort_notice, encode, git_blob

PROTOCOL_PATHS = {"chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md"}
CHECKS = {
    "release": {"healthy", "deployment_identity_matches", "receipt_verified"},
    "sender": {"service_healthy", "outbox_progressing", "no_unresolved_delivery"},
    "retrieve-reliability": {"request_binding_valid", "browser_observation_valid"},
    "retrieve-6aac476f": {"request_binding_valid", "browser_observation_valid"},
    "session-check": {"session_binding_valid", "session_usable"},
    "slot-check": {"bindings_unique", "replacement_verified_before_disable"},
    "lifeguard": {"delivery_ledger_valid", "sender_reachable"},
}


class ProtocolDrift(ValueError):
    pass


def git(bare: Path, *args: str, data: bytes | None = None) -> bytes:
    # stderr is not copied to alerts: Git remote errors can contain credentials.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(["git", "--git-dir=" + str(bare), *args],
                                input=data, stdout=output, stderr=subprocess.DEVNULL,
                                check=False, timeout=90)
        if result.returncode:
            raise RuntimeError("git operation failed")
        if output.tell() > 32 * 1024 * 1024:
            raise RuntimeError("observation too large; state not advanced")
        output.seek(0)
        return output.read()


def batch_blobs(bare: Path, shas: list[str]) -> dict[str, bytes]:
    if not shas:
        return {}
    raw = git(bare, "cat-file", "--batch", data=("\n".join(shas) + "\n").encode())
    position, result = 0, {}
    for expected in shas:
        end = raw.index(b"\n", position)
        sha, kind, size = raw[position:end].split()
        length = int(size)
        position = end + 1
        body = raw[position:position + length]
        position += length
        if sha.decode() != expected or kind != b"blob" or len(body) != length or raw[position:position + 1] != b"\n":
            raise ValueError("invalid batch object")
        if git_blob(body, "sha1" if len(expected) == 40 else "sha256") != expected:
            raise ValueError("Git object checksum failure")
        result[expected] = body
        position += 1
    if position != len(raw):
        raise ValueError("unexpected batch trailing bytes")
    return result


def scan(bare: Path, journal: Journal, approved: dict[str, str]) -> dict[str, Any]:
    if set(approved) != PROTOCOL_PATHS or any(not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", x) for x in approved.values()):
        raise ProtocolDrift("all three approved protocol identities are required")
    bare = bare.resolve(strict=True)
    with (bare / "stage-a-scan.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"exit_code": 11, "status": "BUSY", "model_calls": 0}
        # One network fetch per round. Errors are retried on the next scheduled
        # round, never interpreted as unchanged. There is no HEAD equality test.
        git(bare, "fetch", "--no-tags", "--depth=1", "origin",
            "+refs/heads/chat:refs/remotes/origin/chat")
        snapshot = git(bare, "rev-parse", "refs/remotes/origin/chat").decode().strip()
        raw = git(bare, "ls-tree", "-rz", snapshot, "--", "chat/")
        tree: dict[str, str] = {}
        for record in raw.split(b"\0"):
            if not record:
                continue
            metadata, path_raw = record.split(b"\t", 1)
            mode, kind, sha = metadata.decode("ascii").split()
            path = path_raw.decode("utf-8")
            if path in PROTOCOL_PATHS or (path.startswith("chat/to-hermes/") and path.endswith(".md")):
                if kind != "blob" or mode not in ("100644", "100755"):
                    raise ProtocolDrift("nonregular protocol/source file")
                tree[path] = sha
        if any(tree.get(path) != blob for path, blob in approved.items()):
            raise ProtocolDrift("protocol drift; existing executor remains authoritative")
        sources = {path: sha for path, sha in tree.items() if path.startswith("chat/to-hermes/")}
        with journal.connect() as db:
            known = {(r["source_path"], r["blob_sha"]): r["artifact"] for r in db.execute("SELECT source_path,blob_sha,artifact FROM events")}
        needed = sorted({sha for path, sha in sources.items() if (path, sha) not in known})
        blobs = batch_blobs(bare, needed)
        events = []
        for path, blob in sources.items():
            artifact = known.get((path, blob))
            if artifact is None:
                artifact = journal.store.put(blobs[blob])["sha256"]
            events.append({"source_path": path, "blob_sha": blob,
                           "artifact": artifact, "kind": "relay.reconcile"})
        # One transaction after the complete scan/archives; partial scans never
        # advance seen state. Expired retries remain discoverable on same HEAD.
        added, due = journal.reconcile(events, job="inbox")
        telemetry_degraded = False
        try:
            journal.notice("observe:inbox", active=False, category="observation-recovered")
        except Exception:
            telemetry_degraded = True
            best_effort_notice(journal, "telemetry:inbox", "telemetry-error")
        return {"exit_code": 31 if telemetry_degraded else (10 if due else 0),
                "telemetry_degraded": telemetry_degraded, "status": "WORK" if due else "NO_NEW_EVENT",
                "new_events": added, "due_events": due, "model_calls": 0,
                "network_fetches": 1, "snapshot_commit": snapshot}


def _evaluate(job: str, observation: dict[str, Any], journal: Journal,
              max_age: float = 90.0) -> dict[str, Any]:
    """Validate a trusted local adapter's fresh observation, NOT an LLM verdict.

    Adapters must read actual health/receipt/browser/outbox state. Their exact
    host bindings are deployment inputs and are intentionally not fabricated.
    """
    if job not in CHECKS or set(observation) != {"job", "observed_at", "instance", "revision", "assertions", "work"}:
        raise ProtocolDrift("unknown job or observation schema")
    if observation["job"] != job:
        raise ProtocolDrift("wrong job binding")
    stamp = observation["observed_at"]
    if type(stamp) not in (int, float) or not 0 <= journal.clock() - stamp <= max_age:
        raise ValueError("observation expired or future-dated")
    for name in ("instance", "revision"):
        if not isinstance(observation[name], str) or not observation[name] or len(observation[name]) > 256:
            raise ProtocolDrift("invalid instance/revision binding")
    assertions = observation["assertions"]
    if not isinstance(assertions, dict) or set(assertions) != CHECKS[job] or any(type(x) is not bool for x in assertions.values()):
        raise ProtocolDrift("required health assertions missing or invalid")
    if type(observation["work"]) is not bool:
        raise ProtocolDrift("work must be a boolean")
    failed = sorted(key for key, value in assertions.items() if not value)
    # Polling timestamps are excluded. Revision is the actual deployment,
    # request, sender process epoch, or incident revision, never wall-clock time.
    stable = {key: observation[key] for key in ("job", "instance", "revision", "assertions", "work")}
    content = encode(stable)
    events = []
    if failed or observation["work"]:
        artifact = journal.store.put(content)
        episode = "work"
        if failed:
            with journal.connect() as db:
                prior = db.execute("SELECT active,generation FROM incidents WHERE key=?", ("health:" + job,)).fetchone()
            episode = "episode-" + str((prior["generation"] if prior else 0) + (0 if prior and prior["active"] else 1))
        events.append({"source_path": "local-observations/" + job + "/" + episode + ".json",
                       "blob_sha": git_blob(content), "artifact": artifact["sha256"],
                       "kind": "health.incident" if failed else "deterministic.work"})
    added, due = journal.reconcile(events, job=job, observed_at=stamp)
    telemetry_degraded = False
    try:
        journal.notice("health:" + job, active=bool(failed), category="health-incident")
        journal.notice("observe:" + job, active=False, category="observation-recovered")
    except Exception:
        telemetry_degraded = True
        best_effort_notice(journal, "telemetry:" + job, "telemetry-error")
    return {"exit_code": 31 if telemetry_degraded else (30 if failed else (10 if due else 0)),
            "telemetry_degraded": telemetry_degraded,
            "status": "INCIDENT" if failed else ("WORK" if due else "HEALTHY"),
            "failed_checks": failed, "new_events": added, "due_events": due, "model_calls": 0}



def evaluate(job: str, observation: dict[str, Any], journal: Journal,
             max_age: float = 90.0) -> dict[str, Any]:
    if job not in CHECKS:
        raise ProtocolDrift("unknown job")
    with (journal.root / ("probe-" + job + ".lock")).open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"exit_code": 11, "status": "BUSY", "model_calls": 0}
        return _evaluate(job, observation, journal, max_age)

def observed_call(job: str, function: Any, journal: Journal | None) -> dict[str, Any]:
    try:
        return function()
    except ProtocolDrift:
        best_effort_notice(journal, "observe:" + job, "protocol-drift")
        return {"exit_code": 21, "status": "PROTOCOL_DRIFT", "model_calls": 0}
    except Exception as exc:
        best_effort_notice(journal, "observe:" + job, "observation-error")
        return {"exit_code": 20, "status": "OBSERVATION_ERROR", "error_class": type(exc).__name__, "model_calls": 0}
