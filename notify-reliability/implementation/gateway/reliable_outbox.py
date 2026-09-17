"""Single-host durable outbound delivery. Python 3.11, stdlib only.

ACK means provider acceptance, never that a person read a message.
A worker MUST hold AccountLock throughout recovery, claim and network I/O.
The lock has no TTL: a suspended live process cannot be overtaken unsafely.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import email.utils
import fcntl
import hashlib
import json
import math
import os
import random
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

SCHEMA = """
CREATE TABLE IF NOT EXISTS wx_outbox_messages (
 id TEXT PRIMARY KEY, account TEXT NOT NULL, profile TEXT NOT NULL,
 chat TEXT NOT NULL, source_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 raw TEXT, session_key TEXT, ready INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('preparing','queued','blocked','accepted')),
 category TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
 error TEXT, legacy_id TEXT, alerted INTEGER NOT NULL DEFAULT 0,
 UNIQUE(account,profile,source_key)
);
CREATE TABLE IF NOT EXISTS wx_outbox_parts (
 id TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES wx_outbox_messages(id),
 seq INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('text','file')),
 text TEXT, data BLOB, filename TEXT, force_file INTEGER NOT NULL DEFAULT 0,
 state TEXT NOT NULL CHECK(state IN ('pending','sending','retry','blocked','accepted')),
 attempts INTEGER NOT NULL DEFAULT 0, next_at REAL NOT NULL DEFAULT 0,
 nonce TEXT, ambiguous INTEGER NOT NULL DEFAULT 0, error TEXT,
 accepted_at REAL, UNIQUE(message_id,seq)
);
CREATE TABLE IF NOT EXISTS wx_outbox_accounts (
 account TEXT PRIMARY KEY, profile TEXT NOT NULL, not_before REAL NOT NULL DEFAULT 0,
 heartbeat REAL NOT NULL DEFAULT 0, owner TEXT, paused INTEGER NOT NULL DEFAULT 0,
 last_notice REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS wx_outbox_due ON wx_outbox_parts(state,next_at,message_id,seq);
CREATE INDEX IF NOT EXISTS wx_outbox_message_scope ON wx_outbox_messages(account,profile,state,ready);
"""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def split_exact(text: str, limit: int = 1800) -> list[str]:
    """Lossless O(n) split; budget in UTF-16 units, not an asserted iLink rule.

    Conservative for both code-point and UTF-16 limits. Never trims whitespace
    or adds/closes Markdown fences. The preserved original is the authority.
    """
    if limit < 2:
        raise ValueError("limit must be >= 2")
    out: list[str] = []
    start = used = 0
    for pos, char in enumerate(text):
        cost = 2 if ord(char) > 0xFFFF else 1
        if used + cost > limit:
            out.append(text[start:pos])
            start, used = pos, 0
        used += cost
    if start < len(text):
        out.append(text[start:])
    return out


@dataclasses.dataclass(frozen=True)
class Part:
    kind: str
    text: str = ""
    data: bytes = b""
    filename: str = ""
    force_file: bool = False


class DeliveryError(Exception):
    def __init__(self, code: str, *, retry: bool = True, ambiguous: bool = False,
                 throttle: bool = False, delay: float = 0, account_pause: bool = False):
        # Store only our enumerated code; NEVER raw HTTP response/credentials.
        super().__init__(code)
        self.code = code
        self.retry = retry
        self.ambiguous = ambiguous
        self.throttle = throttle
        self.delay = delay if math.isfinite(delay) and delay >= 0 else 0
        self.account_pause = account_pause


def retry_after(value: str | None, now: float) -> float:
    if not value:
        return 0
    try:
        result = float(value)
    except ValueError:
        try:
            result = email.utils.parsedate_to_datetime(value).timestamp() - now
        except (ValueError, TypeError, OverflowError):
            return 0
    return max(0.0, result) if math.isfinite(result) else 0


def validate_ack(status: int, payload: Any, headers: Any = None,
                 *, now: float | None = None) -> dict[str, Any]:
    """Conservative classification for the supplied iLink adapter contract.

    -2 + 'unknown error' is NOT treated as a frequency limit.
    Empty/invalid responses cannot become success merely because HTTP is 200.
    """
    delay = retry_after((headers or {}).get("Retry-After"), time.time() if now is None else now)
    if status == 429:
        raise DeliveryError("http_rate_limit", throttle=True, delay=max(30, delay))
    if status in (401, 403):
        raise DeliveryError("http_auth", retry=False, account_pause=True)
    if status >= 500 or status in (408, 425):
        raise DeliveryError("http_unknown_outcome", ambiguous=True, delay=delay)
    if not 200 <= status < 300:
        raise DeliveryError("http_rejected", retry=False)
    if not isinstance(payload, dict):
        raise DeliveryError("invalid_ack", retry=False, ambiguous=True, account_pause=True)
    codes = [payload[k] for k in ("ret", "errcode") if k in payload and payload[k] is not None]
    if not codes or any(isinstance(x, bool) or not isinstance(x, int) for x in codes):
        raise DeliveryError("invalid_ack", retry=False, ambiguous=True, account_pause=True)
    msg = str(payload.get("errmsg") or payload.get("msg") or "").strip().lower()
    if -14 in codes or (-2 in codes and msg == "unknown error"):
        raise DeliveryError("session_expired", retry=False, account_pause=True)
    if -2 in codes:
        raise DeliveryError("ilink_rate_limit", throttle=True, delay=max(30, delay))
    if any(c != 0 for c in codes):
        raise DeliveryError("ilink_unclassified_rejection", retry=False)
    return payload


class Store:
    def __init__(self, path: Path | str, *, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Never create an independently writable public spool.
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        if self.path.is_symlink():
            raise ValueError("database_symlink_not_allowed")
        os.chmod(self.path, 0o600)
        with self.connect() as c:
            if c.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
                raise RuntimeError("WAL required on a local filesystem")
            c.executescript(SCHEMA)

    @contextlib.contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA busy_timeout=5000")
            c.execute("PRAGMA synchronous=FULL")
            c.execute("PRAGMA foreign_keys=ON")
            yield c
        finally:
            c.close()

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    def _reserve(self, c: sqlite3.Connection, *, account: str, profile: str, chat: str,
                 key: str, raw: dict, session: str | None, ready: bool,
                 category: str, legacy_id: str | None = None) -> str:
        if not all(isinstance(x, str) and x for x in (account, profile, chat, key)):
            raise ValueError("explicit account/profile/chat/source key required")
        mid = digest(["wx-outbox-v1", account, profile, key])
        fp = digest([chat, raw, session, category])
        existing = c.execute("SELECT fingerprint FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()
        if existing:
            if existing[0] != fp:
                raise ValueError("idempotency_key_payload_conflict")
            return mid
        lane = c.execute("SELECT profile FROM wx_outbox_accounts WHERE account=?", (account,)).fetchone()
        if lane and lane[0] != profile:
            raise ValueError("one_transport_profile_per_account_required")
        c.execute("INSERT OR IGNORE INTO wx_outbox_accounts(account,profile) VALUES (?,?)", (account, profile))
        now = self.clock()
        c.execute("""INSERT INTO wx_outbox_messages
            (id,account,profile,chat,source_key,fingerprint,raw,session_key,ready,
             state,category,created,updated,legacy_id)
            VALUES (?,?,?,?,?,?,?,?,?,'preparing',?,?,?,?)""",
                  (mid, account, profile, chat, key, fp, canonical(raw), session,
                   int(ready), category, now, now, legacy_id))
        return mid

    def reserve(self, **kwargs: Any) -> str:
        conflict = False
        with self.transaction() as c:
            try:
                mid = self._reserve(c, **kwargs)
            except ValueError as exc:
                if str(exc) != "idempotency_key_payload_conflict":
                    raise
                # Preserve BOTH generated artifacts without sending conflicting
                # payloads under one key. Never overwrite the original receipt.
                forensic = dict(kwargs)
                forensic["key"] = "conflict:" + digest([kwargs["key"], kwargs["raw"], kwargs.get("session")])
                forensic["category"] = "conflict"
                mid = self._reserve(c, **forensic)
                c.execute("UPDATE wx_outbox_messages SET state='blocked',error='idempotency_key_payload_conflict' WHERE id=?", (mid,))
                conflict = True
        if conflict:
            raise ValueError("idempotency_key_payload_conflict_preserved:" + mid)
        return mid

    def finish_plan(self, mid: str, parts: list[Part]) -> None:
        if not parts:
            raise ValueError("empty_delivery_plan")
        for p in parts:
            if p.kind not in ("text", "file") or (p.kind == "text" and not p.text):
                raise ValueError("invalid_part")
            if p.kind == "text" and utf16_length(p.text) > 1950:
                raise ValueError("oversized_part")
        with self.transaction() as c:
            row = c.execute("SELECT state FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()
            if not row:
                raise KeyError(mid)
            if row[0] != "preparing":
                return
            for n, p in enumerate(parts):
                pid = digest([mid, n])
                c.execute("""INSERT INTO wx_outbox_parts
                    (id,message_id,seq,kind,text,data,filename,force_file,state)
                    VALUES (?,?,?,?,?,?,?,?,'pending')""",
                          (pid, mid, n, p.kind, p.text, p.data, p.filename, int(p.force_file)))
            c.execute("UPDATE wx_outbox_messages SET state='queued',updated=?,error=NULL WHERE id=?",
                      (self.clock(), mid))

    def activate(self, mid: str) -> None:
        with self.transaction() as c:
            c.execute("UPDATE wx_outbox_messages SET ready=1,updated=? WHERE id=?", (self.clock(), mid))

    def held(self) -> list[dict]:
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT id,session_key FROM wx_outbox_messages WHERE ready=0")]

    def block_plan(self, mid: str, code: str) -> None:
        with self.transaction() as c:
            c.execute("""UPDATE wx_outbox_messages SET state='blocked',error=?,updated=?
                WHERE id=? AND state='preparing'""", (code, self.clock(), mid))

    def unplanned(self, account: str) -> dict | None:
        with self.connect() as c:
            row = c.execute("""SELECT * FROM wx_outbox_messages WHERE account=? AND ready=1
                AND state='preparing' ORDER BY created LIMIT 1""", (account,)).fetchone()
            return dict(row) if row else None

    def recover(self, account: str, owner: str) -> None:
        # Call ONLY after acquiring the kernel lock. Do not guess owner liveness.
        with self.transaction() as c:
            c.execute("""UPDATE wx_outbox_parts SET state='retry',nonce=NULL,ambiguous=1,
                error='worker_interrupted' WHERE state='sending' AND message_id IN
                (SELECT id FROM wx_outbox_messages WHERE account=?)""", (account,))
            c.execute("UPDATE wx_outbox_accounts SET owner=?,heartbeat=? WHERE account=?",
                      (owner, self.clock(), account))

    def heartbeat(self, account: str, owner: str) -> None:
        with self.transaction() as c:
            c.execute("UPDATE wx_outbox_accounts SET heartbeat=?,owner=? WHERE account=?",
                      (self.clock(), owner, account))

    def claim(self, account: str, *, gap: float = 20) -> dict | None:
        now = self.clock()
        with self.transaction() as c:
            lane = c.execute("SELECT * FROM wx_outbox_accounts WHERE account=?", (account,)).fetchone()
            if not lane or lane["paused"] or lane["not_before"] > now:
                return None
            row = c.execute("""SELECT p.*,m.account,m.profile,m.chat,m.category FROM wx_outbox_parts p
                JOIN wx_outbox_messages m ON m.id=p.message_id
                WHERE m.account=? AND m.ready=1 AND m.state='queued'
                  AND p.state IN ('pending','retry') AND p.next_at<=?
                  AND NOT EXISTS (SELECT 1 FROM wx_outbox_parts prev WHERE
                    prev.message_id=p.message_id AND prev.seq<p.seq AND prev.state<>'accepted')
                ORDER BY m.created,p.seq LIMIT 1""", (account, now)).fetchone()
            if not row:
                return None
            result = dict(row)
            nonce = uuid.uuid4().hex
            c.execute("UPDATE wx_outbox_parts SET state='sending',nonce=?,attempts=attempts+1 WHERE id=?",
                      (nonce, result["id"]))
            # Crash during I/O cannot erase the pacing reservation.
            c.execute("UPDATE wx_outbox_accounts SET not_before=? WHERE account=?", (now + gap, account))
            result.update(nonce=nonce, attempts=result["attempts"] + 1)
            return result

    def finish(self, part: dict, error: DeliveryError | None, *, gap: float = 20,
               jitter: Callable[[], float] = random.random) -> None:
        now = self.clock()
        with self.transaction() as c:
            row = c.execute("SELECT state,nonce FROM wx_outbox_parts WHERE id=?", (part["id"],)).fetchone()
            if not row or row[0] != "sending" or row[1] != part["nonce"]:
                raise RuntimeError("stale_completion_fenced")
            mid, account = part["message_id"], part["account"]
            if error is None:
                c.execute("""UPDATE wx_outbox_parts SET state='accepted',accepted_at=?,nonce=NULL,error=NULL
                    WHERE id=?""", (now, part["id"]))
                remaining = c.execute("SELECT 1 FROM wx_outbox_parts WHERE message_id=? AND state<>'accepted' LIMIT 1",
                                      (mid,)).fetchone()
                if not remaining:
                    c.execute("UPDATE wx_outbox_messages SET state='accepted',updated=?,error=NULL WHERE id=?", (now, mid))
                    legacy = c.execute("SELECT legacy_id FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()[0]
                    if legacy:
                        c.execute("""UPDATE delivery_obligations SET state='delivered',updated_at=?,last_error=NULL
                            WHERE obligation_id=? AND state='outbox_managed'""", (now, legacy))
                delay = gap
            else:
                state = "retry" if error.retry else "blocked"
                backoff = min(300.0, 2.0 ** min(part["attempts"], 9)) * (0.5 + 0.5 * jitter())
                delay = max(gap, error.delay, 30 if error.throttle else 0, backoff) + jitter() * 3
                c.execute("""UPDATE wx_outbox_parts SET state=?,next_at=?,nonce=NULL,error=?,
                    ambiguous=MAX(ambiguous,?) WHERE id=?""",
                          (state, now + delay, error.code, int(error.ambiguous), part["id"]))
                c.execute("UPDATE wx_outbox_messages SET error=?,updated=? WHERE id=?", (error.code, now, mid))
                if not error.retry:
                    c.execute("UPDATE wx_outbox_messages SET state='blocked' WHERE id=?", (mid,))
                if error.account_pause:
                    c.execute("UPDATE wx_outbox_accounts SET paused=1 WHERE account=?", (account,))
            c.execute("UPDATE wx_outbox_accounts SET not_before=MAX(not_before,?) WHERE account=?", (now + delay, account))

    def status(self, mid: str) -> dict:
        with self.connect() as c:
            row = c.execute("SELECT id,state,error,ready,created FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()
            if not row:
                raise KeyError(mid)
            result = dict(row)
            result["parts"] = [dict(r) for r in c.execute("""SELECT seq,kind,state,attempts,ambiguous,error,next_at
                FROM wx_outbox_parts WHERE message_id=? ORDER BY seq""", (mid,))]
            return result

    def health(self, account: str) -> dict:
        now = self.clock()
        with self.connect() as c:
            lane = c.execute("SELECT heartbeat,paused,not_before FROM wx_outbox_accounts WHERE account=?", (account,)).fetchone()
            counts = dict(c.execute("SELECT state,COUNT(*) FROM wx_outbox_messages WHERE account=? GROUP BY state", (account,)))
            oldest = c.execute("SELECT MIN(created) FROM wx_outbox_messages WHERE account=? AND state<>'accepted'", (account,)).fetchone()[0]
            ambiguous = c.execute("""SELECT COUNT(*) FROM wx_outbox_parts p JOIN wx_outbox_messages m
                ON m.id=p.message_id WHERE m.account=? AND p.ambiguous=1""", (account,)).fetchone()[0]
            return {"counts": counts, "oldest_pending_seconds": max(0, now-oldest) if oldest is not None else 0,
                    "heartbeat_age_seconds": max(0, now-lane[0]) if lane else None,
                    "paused": bool(lane[1]) if lane else False,
                    "cooldown_seconds": max(0, lane[2]-now) if lane else 0,
                    "ambiguous_parts": ambiguous,
                    "clock_anomaly": bool(lane and lane[0] > now + 5) or bool(oldest is not None and oldest > now + 5),
                    "database_bytes": self.path.stat().st_size,
                    "disk_free_bytes": os.statvfs(self.path.parent).f_bavail * os.statvfs(self.path.parent).f_frsize}

    def resume(self, account: str) -> None:
        """Explicit operator action after fixing authentication/content/storage."""
        with self.transaction() as c:
            c.execute("UPDATE wx_outbox_accounts SET paused=0 WHERE account=?", (account,))
            c.execute("""UPDATE wx_outbox_parts SET state='retry',next_at=0 WHERE state='blocked'
                AND message_id IN (SELECT id FROM wx_outbox_messages WHERE account=?)""", (account,))
            c.execute("""UPDATE wx_outbox_messages SET state=CASE WHEN EXISTS
                (SELECT 1 FROM wx_outbox_parts p WHERE p.message_id=wx_outbox_messages.id)
                THEN 'queued' ELSE 'preparing' END,error=NULL WHERE account=? AND state='blocked' AND category<>'conflict'""", (account,))

    def scrub_accepted_payloads(self, days: int = 7) -> int:
        if days < 1:
            raise ValueError("retention must be >= one day")
        with self.transaction() as c:
            cutoff = self.clock() - days * 86400
            c.execute("""UPDATE wx_outbox_parts SET text=NULL,data=NULL WHERE (text IS NOT NULL OR data IS NOT NULL) AND message_id IN
                (SELECT id FROM wx_outbox_messages WHERE state='accepted' AND updated<?)""", (cutoff,))
            return c.execute("UPDATE wx_outbox_messages SET raw=NULL WHERE state='accepted' AND updated<? AND raw IS NOT NULL",
                             (cutoff,)).rowcount

    def notice(self, account: str) -> None:
        """One bounded delay notice per 10 minutes; notices cannot alert on themselves."""
        now = self.clock()
        with self.transaction() as c:
            lane = c.execute("SELECT last_notice FROM wx_outbox_accounts WHERE account=?", (account,)).fetchone()
            if not lane or (lane[0] and now-lane[0] < 600):
                return
            rows = c.execute("""SELECT id,profile,chat FROM wx_outbox_messages WHERE account=?
                AND state<>'accepted' AND category<>'notice' AND alerted=0 AND (created<? OR state='blocked')""",
                             (account, now-120)).fetchall()
            if not rows:
                return
            # One per affected peer, never disclose another peer's pending count.
            for profile, chat in sorted({(r[1], r[2]) for r in rows}):
                count = sum(r[1] == profile and r[2] == chat for r in rows)
                raw = {"type": "text", "body": f"【交付状态】有 {count} 条消息尚未获得微信接收确认，内容已保存。临时故障会自动补发；登录或内容拒绝需要修复。回执不确定时可能重复，消息编号不变。"}
                self._reserve(c, account=account, profile=profile, chat=chat,
                              key=f"notice:{int(now)}:{chat}", raw=raw, session=None,
                              ready=True, category="notice")
            for row in rows:
                c.execute("UPDATE wx_outbox_messages SET alerted=1 WHERE id=?", (row[0],))
            c.execute("UPDATE wx_outbox_accounts SET last_notice=? WHERE account=?", (now, account))

    def import_legacy(self, account: str, profile: str, ids: list[str], *, apply: bool = False) -> list[dict]:
        """Gateway and legacy sender must be stopped; same-db ownership transfer."""
        with self.transaction() as c:
            rows = []
            for oid in ids:
                r = c.execute("SELECT * FROM delivery_obligations WHERE obligation_id=?", (oid,)).fetchone()
                if not r:
                    raise ValueError("legacy_id_not_found")
                if r["platform"] != "weixin" or (r["adapter_profile"] or "default") != profile:
                    raise ValueError("legacy_route_mismatch")
                if r["state"] == "outbox_managed":
                    continue
                if r["state"] not in ("pending", "attempting", "failed"):
                    raise ValueError("legacy_state_not_replayable")
                rows.append(dict(r))
            if apply:
                for r in rows:
                    # Old sends may have delivered an unknown prefix. Do not claim no duplicates.
                    mid = self._reserve(c, account=account, profile=profile, chat=r["chat_id"],
                                        key="legacy:"+r["obligation_id"],
                                        raw={"type": "text", "body": "【历史补发，可能重复】\n"+r["content"]},
                                        session=r["session_key"], ready=False, category="legacy",
                                        legacy_id=r["obligation_id"])
                    c.execute("UPDATE delivery_obligations SET state='outbox_managed' WHERE obligation_id=?", (r["obligation_id"],))
            return [{"id": r["obligation_id"], "state": r["state"], "length": len(r["content"])} for r in rows]


class AccountLock:
    def __init__(self, directory: Path, account: str):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / (digest(["account-lock", account]) + ".lock")
        self.fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            raise

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> AccountLock:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class Transport(Protocol):
    async def send(self, part: dict) -> None: ...


async def run_io(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """Do not release process ownership while a cancelled DB thread still runs."""
    task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        try:
            await task
        except Exception:
            pass
        raise


class Worker:
    def __init__(self, store: Store, account: str, transport: Transport, *, gap: float = 20,
                 jitter: Callable[[], float] = random.random):
        self.store, self.account, self.transport = store, account, transport
        self.gap, self.jitter = gap, jitter

    async def step(self) -> bool:
        part = await run_io(self.store.claim, self.account, gap=self.gap)
        if not part:
            return False
        failure = None
        try:
            await self.transport.send(part)
        except DeliveryError as exc:
            failure = exc
        except asyncio.CancelledError:
            # Leave sending durable; recovery marks it ambiguous after lock takeover.
            raise
        except Exception:
            failure = DeliveryError("transport_exception", ambiguous=True)
        await run_io(self.store.finish, part, failure, gap=self.gap, jitter=self.jitter)
        return True
