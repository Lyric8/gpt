from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterator


def encode(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes, algorithm: str = "sha1") -> str:
    if algorithm not in ("sha1", "sha256"):
        raise ValueError("unsupported Git object format")
    return hashlib.new(algorithm, b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def private_dir(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("private directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def atomic_write(path: Path, data: bytes) -> None:
    private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


class Store:
    def __init__(self, root: Path):
        self.root = root
        private_dir(root)

    def put(self, data: bytes) -> dict[str, Any]:
        key = sha256(data)
        path = self.root / key
        if path.exists():
            self.get(key)
        else:
            atomic_write(path, data)
        return {"sha256": key, "bytes": len(data)}

    def put_json(self, data: Any) -> dict[str, Any]:
        return self.put(encode(data))

    def get(self, key: str) -> bytes:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("invalid content address")
        path = self.root / key
        if path.is_symlink():
            raise ValueError("artifact symlink forbidden")
        data = path.read_bytes()
        if sha256(data) != key:
            raise ValueError("artifact integrity failure")
        return data

    def read_range(self, key: str, offset: int, length: int) -> bytes:
        if offset < 0 or not 0 < length <= 65536:
            raise ValueError("invalid byte range")
        # Verify the complete object before returning a range. This is byte,
        # not token, accounting; the existing tool adapter counts returned text.
        return self.get(key)[offset:offset + length]


class Journal:
    """Local observation/outbox only. Never grants remote execution authority."""
    def __init__(self, root: Path, clock: Callable[[], float] = time.time):
        private_dir(root)
        self.root, self.clock = root, clock
        self.store = Store(root / "objects")
        self.db = root / "stage_a.sqlite3"
        if self.db.is_symlink():
            raise ValueError("database symlink forbidden")
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events(
                  id TEXT PRIMARY KEY, source_path TEXT NOT NULL,
                  blob_sha TEXT NOT NULL, artifact TEXT NOT NULL,
                  kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING', proof_sha TEXT,
                  available REAL NOT NULL,
                  UNIQUE(source_path,blob_sha));
                CREATE TABLE IF NOT EXISTS incidents(
                  key TEXT PRIMARY KEY, active INTEGER NOT NULL,
                  generation INTEGER NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS alerts(
                  id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                  state TEXT NOT NULL DEFAULT 'PENDING',
                  available REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                  sender_receipt TEXT);
                CREATE TABLE IF NOT EXISTS attempt_records(
                  attempt_id TEXT NOT NULL, phase TEXT NOT NULL,
                  root_task_id TEXT NOT NULL, session_id TEXT NOT NULL,
                  segment_id TEXT NOT NULL, usage_json TEXT NOT NULL,
                  recorded_at REAL NOT NULL, PRIMARY KEY(attempt_id,phase));
                CREATE TABLE IF NOT EXISTS observations(
                  job TEXT PRIMARY KEY, observed_at REAL NOT NULL);
            """)
        self.db.chmod(0o600)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db, timeout=0.15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def reconcile(self, events: list[dict[str, Any]], *, job: str,
                  observed_at: float | None = None) -> tuple[int, int]:
        prepared = []
        for event in events:
            path, blob = event["source_path"], event["blob_sha"]
            data = self.store.get(event["artifact"])
            if git_blob(data, "sha1" if len(blob) == 40 else "sha256") != blob:
                raise ValueError("source blob does not match archived bytes")
            identity = sha256(encode([path, blob]))
            prepared.append((identity, path, blob, event["artifact"], event["kind"]))
        count = 0
        with self.transaction() as db:
            if observed_at is not None:
                previous = db.execute("SELECT observed_at FROM observations WHERE job=?", (job,)).fetchone()
                if previous and observed_at <= previous[0]:
                    raise ValueError("stale or replayed observation")
            for identity, path, blob, artifact, kind in prepared:
                old = db.execute("SELECT artifact FROM events WHERE id=?", (identity,)).fetchone()
                if old and old[0] != artifact:
                    raise ValueError("same source identity has conflicting bytes")
                count += db.execute("INSERT OR IGNORE INTO events(id,source_path,blob_sha,artifact,kind,available) VALUES(?,?,?,?,?,?)",
                                    (identity, path, blob, artifact, kind, self.clock())).rowcount
            if observed_at is not None:
                db.execute("INSERT INTO observations VALUES(?,?) ON CONFLICT(job) DO UPDATE SET observed_at=excluded.observed_at",
                           (job, observed_at))
            due = db.execute("SELECT COUNT(*) FROM events WHERE state='PENDING' AND available<=?", (self.clock(),)).fetchone()[0]
        return count, due

    def record_attempt(self, *, attempt_id: str, root_task_id: str,
                       session_id: str, segment_id: str, phase: str,
                       usage: dict[str, int | None]) -> None:
        if not all(isinstance(x, str) and x for x in (attempt_id, root_task_id, session_id, segment_id)):
            raise ValueError("stable attempt/root/session/segment identities required")
        if phase not in ("attempt", "usage", "failed", "cancelled"):
            raise ValueError("unsupported physical-attempt phase")
        allowed = {"input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens"}
        if not set(usage) <= allowed or any(x is not None and (type(x) is not int or x < 0) for x in usage.values()):
            raise ValueError("usage must contain only normalized numeric counters")
        fields = (attempt_id, phase, root_task_id, session_id, segment_id, encode(usage).decode())
        with self.transaction() as db:
            old = db.execute("SELECT root_task_id,session_id,segment_id,usage_json FROM attempt_records WHERE attempt_id=? AND phase=?", fields[:2]).fetchone()
            if old and tuple(old) != fields[2:]:
                raise ValueError("attempt identity reused for different accounting")
            db.execute("INSERT OR IGNORE INTO attempt_records VALUES(?,?,?,?,?,?,?)", fields + (self.clock(),))

    def reconcile_completed(self, event_id: str, proof: dict[str, Any],
                            verify: Callable[[dict[str, Any], dict[str, Any]], bool]) -> None:
        # verify is a trusted host adapter that reads authoritative remote and
        # business state. A model-supplied verified=true is never sufficient.
        with self.connect() as db:
            row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("unknown event")
        event = dict(row)
        if proof.get("source_path") != event["source_path"] or proof.get("blob_sha") != event["blob_sha"]:
            raise ValueError("completion proof belongs to another source")
        if verify(event, proof) is not True:
            raise ValueError("authoritative completion not verified")
        artifact = self.store.put_json(proof)["sha256"]
        with self.transaction() as db:
            db.execute("UPDATE events SET state='DONE',proof_sha=? WHERE id=?", (artifact, event_id))

    def notice(self, key: str, *, active: bool, category: str) -> str | None:
        """One alert per incident episode; clocks/error text are not identity."""
        with self.transaction() as db:
            previous = db.execute("SELECT * FROM incidents WHERE key=?", (key,)).fetchone()
            if previous and bool(previous["active"]) == active:
                db.execute("UPDATE incidents SET updated=? WHERE key=?", (self.clock(), key))
                return None
            if previous is None and not active:
                return None
            generation = (previous["generation"] if previous else 0) + (1 if active else 0)
            db.execute("INSERT INTO incidents VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET active=excluded.active,generation=excluded.generation,updated=excluded.updated",
                       (key, int(active), generation, self.clock()))
            identity = sha256(encode([key, generation, active]))
            # No raw exceptions, URLs, credentials, prompts, or command lines.
            payload = {"idempotency_key": identity, "kind": category,
                       "subject_key_sha256": sha256(key.encode()),
                       "generation": generation, "active": active, "blocking": False}
            db.execute("INSERT OR IGNORE INTO alerts(id,payload,available) VALUES(?,?,?)",
                       (identity, encode(payload).decode(), self.clock()))
            return identity

    def drain(self, enqueue: Callable[[dict[str, Any]], dict[str, Any]], limit: int = 50) -> int:
        """Transfer to existing durable sender; HANDOFF is not DELIVERED.

        Run outside gateway; enqueue MUST implement idempotency_key and return
        only after durable acceptance. Crash after acceptance is safe to retry.
        """
        import fcntl
        if limit < 1:
            raise ValueError("invalid batch size")
        done = 0
        with (self.root / "sender-handoff.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            with self.connect() as db:
                rows = list(db.execute("SELECT * FROM alerts WHERE state='PENDING' AND available<=? ORDER BY available,id LIMIT ?",
                                       (self.clock(), limit)))
            for row in rows:
                try:
                    response = enqueue(json.loads(row["payload"]))
                    if response.get("durable") is not True or not isinstance(response.get("receipt_id"), str) or not response["receipt_id"]:
                        raise ValueError("sender has not durably accepted alert")
                    with self.transaction() as db:
                        db.execute("UPDATE alerts SET state='HANDOFF',sender_receipt=? WHERE id=?",
                                   (response["receipt_id"], row["id"]))
                    done += 1
                except Exception:
                    with self.transaction() as db:
                        db.execute("UPDATE alerts SET attempts=attempts+1,available=? WHERE id=?",
                                   (self.clock() + min(600, 30 * 2 ** min(row["attempts"], 5)), row["id"]))
        return done


def best_effort_notice(journal: Journal | None, key: str, category: str) -> None:
    try:
        if journal is not None:
            journal.notice(key, active=True, category=category)
            return
    except Exception:
        pass
    # Last-resort diagnostics contain no exception text or user payload.
    try:
        os.write(2, b"stage_a: telemetry_unavailable; owner_request_not_blocked\n")
    except OSError:
        pass
