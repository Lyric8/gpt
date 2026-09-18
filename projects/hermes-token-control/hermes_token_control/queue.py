from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .artifacts import Artifacts, canonical, digest
from .governor import IntegrityError


class EventQueue:
    """Local scheduling journal, NEVER a replacement for Git message/resource leases.

    Atomic scan + cursor; stable event identity; expiring leases with epochs.
    Remote mutations still require the current chat protocol and external CAS.
    """
    def __init__(self, db: str | Path, store: Artifacts,
                 clock: Callable[[], float] = time.time):
        self.db, self.store, self.clock = str(Path(db).resolve()), store, clock
        Path(self.db).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.tx() as c:
            for sql in (
                "CREATE TABLE IF NOT EXISTS cursors(channel TEXT PRIMARY KEY, value TEXT NOT NULL)",
                """CREATE TABLE IF NOT EXISTS events(
                  id TEXT PRIMARY KEY, channel TEXT NOT NULL, item_key TEXT NOT NULL,
                  version TEXT NOT NULL, payload_sha TEXT NOT NULL, state TEXT NOT NULL,
                  owner TEXT, epoch INTEGER NOT NULL DEFAULT 0, expires REAL,
                  attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL,
                  receipt_sha TEXT, UNIQUE(channel,item_key,version))""",
                """CREATE TABLE IF NOT EXISTS outbox(
                  id TEXT PRIMARY KEY REFERENCES events(id), body TEXT NOT NULL,
                  state TEXT NOT NULL, acknowledgment TEXT)""",
                "CREATE INDEX IF NOT EXISTS events_due ON events(state,available,expires)",
            ):
                c.execute(sql)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=FULL")
            c.execute("PRAGMA busy_timeout=10000")
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def cursor(self, channel: str) -> str | None:
        with self.tx() as c:
            r = c.execute("SELECT value FROM cursors WHERE channel=?", (channel,)).fetchone()
            return r[0] if r else None

    def ingest(self, channel: str, expected_cursor: str | None, new_cursor: str,
               events: list[dict[str, Any]]) -> int:
        if not channel or not new_cursor:
            raise ValueError("channel and cursor cannot be empty")
        prepared = []
        for event in events:
            if not isinstance(event.get("key"), str) or not event["key"]:
                raise ValueError("event key required")
            if not isinstance(event.get("version"), str) or not event["version"]:
                raise ValueError("immutable event version required")
            ref = self.store.put_json(event)
            eid = digest([channel, event["key"], event["version"]])
            prepared.append((eid, event, ref))
        inserted = 0
        with self.tx() as c:
            row = c.execute("SELECT value FROM cursors WHERE channel=?", (channel,)).fetchone()
            actual = row[0] if row else None
            if actual != expected_cursor:
                raise IntegrityError("scanner cursor CAS conflict; rescan, never overwrite")
            for eid, event, ref in prepared:
                row = c.execute("SELECT payload_sha FROM events WHERE id=?", (eid,)).fetchone()
                if row and row[0] != ref["sha256"]:
                    raise IntegrityError("same event identity with different payload")
                inserted += c.execute("""INSERT OR IGNORE INTO events
                    (id,channel,item_key,version,payload_sha,state,available)
                    VALUES(?,?,?,?,?,'PENDING',?)""",
                    (eid, channel, event["key"], event["version"], ref["sha256"], self.clock())).rowcount
            c.execute("INSERT INTO cursors VALUES(?,?) ON CONFLICT(channel) DO UPDATE SET value=excluded.value",
                      (channel, new_cursor))
        return inserted

    def _with_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = json.loads(self.store.read(row["payload_sha"]))
        return result

    def peek_due(self, *, channel: str | None = None, max_attempts: int = 5) -> dict[str, Any] | None:
        """Read the oldest due event without changing attempts/lease state.

        Stage-1 dispatch uses this before any local claim so remote completion and
        STATUS can be re-read first. Remote uncertainty therefore does not consume
        a local attempt or grant execution authority.
        """
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        now = self.clock()
        where_channel = " AND channel=?" if channel is not None else ""
        params: tuple[Any, ...] = (now, max_attempts, now) + ((channel,) if channel is not None else ())
        with self.tx() as c:
            row = c.execute(
                """SELECT * FROM events WHERE available<=? AND attempts<? AND
                   (state='PENDING' OR (state='RUNNING' AND expires<=?))"""
                + where_channel + " ORDER BY available,id LIMIT 1",
                params,
            ).fetchone()
            return self._with_payload(row) if row is not None else None

    def claim(self, owner: str, *, ttl: float = 120, max_attempts: int = 5) -> dict[str, Any] | None:
        if not owner or not 0 < ttl <= 3600 or max_attempts <= 0:
            raise ValueError("invalid lease policy")
        now = self.clock()
        with self.tx() as c:
            c.execute("""UPDATE events SET state='BLOCKED' WHERE attempts>=? AND
                      (state='PENDING' OR (state='RUNNING' AND expires<=?))""", (max_attempts, now))
            row = c.execute("""SELECT * FROM events WHERE available<=? AND attempts<? AND
                  (state='PENDING' OR (state='RUNNING' AND expires<=?)) ORDER BY available,id LIMIT 1""",
                  (now, max_attempts, now)).fetchone()
            if row is None:
                return None
            epoch = row["epoch"] + 1
            c.execute("UPDATE events SET state='RUNNING',owner=?,epoch=?,expires=?,attempts=attempts+1 WHERE id=?",
                      (owner, epoch, now + ttl, row["id"]))
            result = dict(row)
            result.update(owner=owner, epoch=epoch, expires=now+ttl, state="RUNNING",
                          attempts=row["attempts"]+1)
            result["payload"] = json.loads(self.store.read(row["payload_sha"]))
            return result

    def claim_specific(self, event: str, owner: str, expected_version: str, *,
                       ttl: float = 120, max_attempts: int = 5) -> dict[str, Any] | None:
        """Claim exactly the event that passed the remote pre-claim gate."""
        if not event or not owner or not expected_version or not 0 < ttl <= 3600 or max_attempts <= 0:
            raise ValueError("invalid specific-claim policy")
        now = self.clock()
        with self.tx() as c:
            row = c.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
            if row is None:
                return None
            if row["version"] != expected_version:
                raise IntegrityError("event version changed under specific claim")
            due = row["available"] <= now and (
                row["state"] == "PENDING" or
                (row["state"] == "RUNNING" and row["expires"] is not None and row["expires"] <= now)
            )
            if not due:
                return None
            if row["attempts"] >= max_attempts:
                c.execute("UPDATE events SET state='BLOCKED',owner=NULL,expires=NULL WHERE id=?", (event,))
                return None
            epoch = row["epoch"] + 1
            expires = now + ttl
            c.execute(
                "UPDATE events SET state='RUNNING',owner=?,epoch=?,expires=?,attempts=attempts+1 WHERE id=?",
                (owner, epoch, expires, event),
            )
            result = dict(row)
            result.update(owner=owner, epoch=epoch, expires=expires, state="RUNNING",
                          attempts=row["attempts"] + 1)
            result["payload"] = json.loads(self.store.read(row["payload_sha"]))
            return result

    def _owned(self, c: sqlite3.Connection, event: str, owner: str, epoch: int) -> sqlite3.Row:
        row = c.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
        if row is None or row["state"] != "RUNNING" or row["owner"] != owner or row["epoch"] != epoch:
            raise IntegrityError("stale or foreign local lease")
        if row["expires"] <= self.clock():
            raise IntegrityError("local lease expired; reconcile before takeover")
        return row

    def owned_event(self, event: str, owner: str, epoch: int) -> dict[str, Any]:
        with self.tx() as c:
            return self._with_payload(self._owned(c, event, owner, epoch))

    def renew(self, event: str, owner: str, epoch: int, *, ttl: float = 120) -> None:
        if not 0 < ttl <= 3600:
            raise ValueError("invalid lease TTL")
        with self.tx() as c:
            self._owned(c, event, owner, epoch)
            c.execute("UPDATE events SET expires=? WHERE id=?", (self.clock()+ttl, event))

    def defer(self, event: str, owner: str, epoch: int, *, delay: float, reason: str) -> None:
        if delay < 0 or not reason:
            raise ValueError("defer requires nonnegative delay and reason")
        ref = self.store.put_json({"reason": reason, "at": self.clock()})
        with self.tx() as c:
            self._owned(c, event, owner, epoch)
            c.execute("UPDATE events SET state='PENDING',available=?,owner=NULL,expires=NULL,receipt_sha=? WHERE id=?",
                      (self.clock()+delay, ref["sha256"], event))

    def release_claim(self, event: str, owner: str, epoch: int, *, delay: float,
                      reason: str, refund_attempt: bool = True) -> None:
        """Fail closed after a gate/read error without burning the business retry budget."""
        if delay < 0 or not reason:
            raise ValueError("release requires nonnegative delay and reason")
        ref = self.store.put_json({"reason": reason, "at": self.clock(), "gate_release": True})
        with self.tx() as c:
            row = self._owned(c, event, owner, epoch)
            attempts = row["attempts"] - 1 if refund_attempt and row["attempts"] > 0 else row["attempts"]
            c.execute(
                """UPDATE events SET state='PENDING',available=?,owner=NULL,expires=NULL,
                   attempts=?,receipt_sha=? WHERE id=?""",
                (self.clock() + delay, attempts, ref["sha256"], event),
            )

    def reconcile_remote(self, event: str, expected_version: str, *, state: str,
                         evidence: dict[str, Any]) -> None:
        """Close an unclaimed/expired local event from authoritative remote readback.

        This does not enqueue a notification: the business action already ended
        remotely or the source explicitly says no action is required.
        """
        if state not in ("REMOTE_COMPLETED", "NON_REQUEST"):
            raise ValueError("invalid reconciliation state")
        if evidence.get("source_blob_sha") != expected_version:
            raise IntegrityError("reconciliation evidence does not bind the event version")
        ref = self.store.put_json(evidence)
        now = self.clock()
        with self.tx() as c:
            row = c.execute("SELECT * FROM events WHERE id=?", (event,)).fetchone()
            if row is None:
                raise IntegrityError("unknown event")
            if row["version"] != expected_version:
                raise IntegrityError("reconciliation applies to another source version")
            if row["state"] in ("DONE", "REMOTE_COMPLETED", "NON_REQUEST"):
                return
            if row["state"] == "RUNNING" and row["expires"] is not None and row["expires"] > now:
                raise IntegrityError("cannot reconcile an event owned by another active local worker")
            c.execute(
                "UPDATE events SET state=?,owner=NULL,expires=NULL,receipt_sha=? WHERE id=?",
                (state, ref["sha256"], event),
            )

    def reconcile_owned_remote(self, event: str, owner: str, epoch: int, *, state: str,
                               evidence: dict[str, Any]) -> None:
        if state not in ("REMOTE_COMPLETED", "NON_REQUEST"):
            raise ValueError("invalid reconciliation state")
        ref = self.store.put_json(evidence)
        with self.tx() as c:
            row = self._owned(c, event, owner, epoch)
            if evidence.get("source_blob_sha") != row["version"]:
                raise IntegrityError("reconciliation evidence does not bind the owned source version")
            c.execute(
                "UPDATE events SET state=?,owner=NULL,expires=NULL,receipt_sha=? WHERE id=?",
                (state, ref["sha256"], event),
            )

    def finish_local(self, event: str, owner: str, epoch: int, receipt: dict[str, Any]) -> None:
        """Caller has already read-back-verified remote completion and all required checks.

        Local finish + notification enqueue are atomic. Notification transport is
        existing campfire-sender, not an LLM. No external exactly-once is claimed.
        """
        if receipt.get("event_id") != event or receipt.get("status") != "VERIFIED":
            raise IntegrityError("unverified/mismatched receipt")
        for field in ("source_version", "remote_receipt_sha", "remote_completion_sha"):
            if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", str(receipt.get(field, ""))):
                raise IntegrityError("missing verified remote identity: " + field)
        checks = receipt.get("checks")
        if not isinstance(checks, dict) or not checks or any(v is not True for v in checks.values()):
            raise IntegrityError("missing/failed verification checks")
        ref = self.store.put_json(receipt)
        with self.tx() as c:
            row = self._owned(c, event, owner, epoch)
            if receipt["source_version"] != row["version"]:
                raise IntegrityError("receipt applies to another source version")
            payload = json.loads(self.store.read(row["payload_sha"]))
            required = set(payload.get("required_checks", []))
            if not required or not required.issubset(checks):
                raise IntegrityError("required verification set not satisfied")
            c.execute("UPDATE events SET state='DONE',receipt_sha=? WHERE id=?", (ref["sha256"], event))
            c.execute("INSERT INTO outbox VALUES(?,?,'PENDING',NULL)",
                      (event, canonical({"event_id": event, "receipt": ref}).decode()))

    def pending_notifications(self) -> list[dict[str, Any]]:
        with self.tx() as c:
            return [dict(r) for r in c.execute("SELECT * FROM outbox WHERE state='PENDING' ORDER BY id")]

    def acknowledge_notification(self, event: str, durable_sender_ack: str) -> None:
        if not durable_sender_ack:
            raise IntegrityError("notification acknowledgment required")
        with self.tx() as c:
            row = c.execute("SELECT * FROM outbox WHERE id=?", (event,)).fetchone()
            if row is None:
                raise IntegrityError("unknown notification")
            if row["state"] == "DELIVERED" and row["acknowledgment"] != durable_sender_ack:
                raise IntegrityError("conflicting notification acknowledgment")
            c.execute("UPDATE outbox SET state='DELIVERED',acknowledgment=? WHERE id=?",
                      (durable_sender_ack, event))
