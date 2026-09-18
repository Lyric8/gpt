from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .artifacts import Artifacts, canonical, digest


class BudgetStop(RuntimeError):
    """Catch OUTSIDE all provider-retry loops. Persist/surface WAITING_BUDGET, not DONE."""


class IntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class Policy:
    input_hard: int = 64_000
    calls_per_segment: int = 8
    task_calls: int = 24
    task_input: int = 1_024_000
    task_output: int = 160_000
    max_segments: int = 3
    output_per_call: int = 8_000

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in asdict(self).values()):
            raise ValueError("all policy limits must be positive integers")
        if self.task_calls < self.calls_per_segment:
            raise ValueError("task call budget is smaller than a segment")


POLICIES = {
    "interactive": Policy(),
    "incident": Policy(input_hard=24_000, calls_per_segment=4, task_calls=8,
                       task_input=128_000, task_output=48_000,
                       max_segments=2, output_per_call=8_000),
    "engineering": Policy(input_hard=64_000, calls_per_segment=12, task_calls=36,
                          task_input=1_536_000, task_output=384_000,
                          max_segments=3, output_per_call=16_000),
}


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    method: str
    certified_upper_bound: bool = False

    def __post_init__(self) -> None:
        if type(self.tokens) is not int or self.tokens < 0 or not self.method:
            raise ValueError("invalid token count")


@dataclass(frozen=True)
class Usage:
    uncached: int
    cache_read: int
    output: int
    cache_write: int = 0
    reasoning_subset: int = 0

    def __post_init__(self) -> None:
        if any(type(v) is not int or v < 0 for v in asdict(self).values()):
            raise ValueError("usage counters must be nonnegative integers")
        if self.reasoning_subset > self.output:
            raise ValueError("reasoning tokens exceed total output")

    @property
    def prompt(self) -> int:
        return self.uncached + self.cache_read + self.cache_write

    @classmethod
    def from_chat_completions(cls, raw: Mapping[str, Any]) -> Usage:
        """OpenAI-compatible / DeepSeek usage. NOT Anthropic Messages usage."""
        def n(value: Any) -> int:
            if type(value) is not int or value < 0:
                raise ValueError("invalid/missing provider usage")
            return value
        total = n(raw.get("prompt_tokens"))
        output = n(raw.get("completion_tokens"))
        hit = n(raw.get("prompt_cache_hit_tokens",
                        (raw.get("prompt_tokens_details") or {}).get("cached_tokens", 0)))
        miss = n(raw.get("prompt_cache_miss_tokens", total - hit))
        if hit + miss != total:
            raise ValueError("provider prompt buckets do not reconcile")
        reasoning = n((raw.get("completion_tokens_details") or {}).get("reasoning_tokens", 0))
        return cls(miss, hit, output, reasoning_subset=reasoning)


class Governor:
    """One SQLite transaction per admission; counts failed attempts and all segments.

    SDK retries MUST be disabled. Every physical send, fallback and auxiliary call
    goes through admit(). No token budget is reset by opening a new session.
    """
    def __init__(self, db: str | Path, artifacts: Artifacts,
                 clock: Callable[[], float] = time.time):
        self.db = str(Path(db).resolve())
        Path(self.db).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.artifacts, self.clock = artifacts, clock
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS tasks(
                id TEXT PRIMARY KEY, policy TEXT NOT NULL, status TEXT NOT NULL,
                segment INTEGER NOT NULL DEFAULT 0, checkpoint TEXT NOT NULL,
                created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id),
                segment INTEGER NOT NULL, request_sha TEXT NOT NULL,
                input_bound INTEGER NOT NULL, output_bound INTEGER NOT NULL,
                method TEXT NOT NULL, state TEXT NOT NULL, usage TEXT,
                error TEXT, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_task ON attempts(task, segment);
            CREATE TABLE IF NOT EXISTS budget_approvals(
                id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id),
                previous_policy TEXT NOT NULL, new_policy TEXT NOT NULL,
                approved_by TEXT NOT NULL, reason TEXT NOT NULL, created REAL NOT NULL);
            """)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA busy_timeout=10000")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=FULL")
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def begin(self, task: str, checkpoint: Mapping[str, Any], policy: Policy) -> None:
        self._validate_checkpoint(task, checkpoint)
        ref = self.artifacts.put_json(checkpoint)
        p = canonical(asdict(policy)).decode()
        with self.transaction() as c:
            row = c.execute("SELECT policy, checkpoint FROM tasks WHERE id=?", (task,)).fetchone()
            if row is not None:
                if row["policy"] != p:
                    raise IntegrityError("task policy cannot change on retry/resume")
                original = json.loads(self.artifacts.read(row["checkpoint"]))
                if original["goal"] != checkpoint["goal"] or original["constraints"] != checkpoint["constraints"]:
                    raise IntegrityError("existing task identity cannot be reused for a different goal")
                return
            c.execute("INSERT INTO tasks VALUES(?,?,?,0,?,?)",
                      (task, p, "RUNNING", ref["sha256"], self.clock()))

    @staticmethod
    def _validate_checkpoint(task: str, checkpoint: Mapping[str, Any]) -> None:
        required = {"task_id", "goal", "constraints", "source_versions",
                    "verified", "pending", "next_actions"}
        if not required.issubset(checkpoint) or checkpoint["task_id"] != task:
            raise IntegrityError("checkpoint lacks task identity or required state fields")
        if not task or not isinstance(checkpoint["goal"], str) or not checkpoint["goal"]:
            raise IntegrityError("empty task/goal")
        for key in ("constraints", "verified", "pending", "next_actions"):
            if not isinstance(checkpoint[key], list):
                raise IntegrityError(f"checkpoint {key} must be a list")
        if not isinstance(checkpoint["source_versions"], dict):
            raise IntegrityError("source_versions must be a mapping")

    def admit(self, task: str, request: Mapping[str, Any], count: TokenCount,
              output_bound: int) -> str:
        if not count.certified_upper_bound:
            raise BudgetStop("uncertified tokenizer: measurement only; production send refused")
        if type(output_bound) is not int or output_bound <= 0:
            raise ValueError("output bound must be positive")
        ref = self.artifacts.put_json(request)
        stop = None
        request_id = str(uuid.uuid4())
        with self.transaction() as c:
            t = c.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None:
                raise IntegrityError("unknown task")
            p = Policy(**json.loads(t["policy"]))
            rows = c.execute("SELECT * FROM attempts WHERE task=?", (task,)).fetchall()
            used_in = used_out = segment_calls = 0
            for row in rows:
                u = Usage(**json.loads(row["usage"])) if row["usage"] else None
                used_in += max(row["input_bound"], u.prompt if u else 0)
                used_out += u.output if u else row["output_bound"]
                segment_calls += row["segment"] == t["segment"]
            if t["status"] != "RUNNING":
                stop = f"task status is {t['status']}"
            elif any(r["state"] == "IN_FLIGHT" for r in rows):
                raise IntegrityError("prior attempt is unresolved; reconcile it before another send")
            elif count.tokens > p.input_hard:
                stop = "input hard cap: archive/compact/retrieve targeted evidence"
            elif output_bound > p.output_per_call:
                stop = "output reservation exceeds profile cap"
            elif segment_calls >= p.calls_per_segment:
                stop = "segment attempt limit"
            elif len(rows) >= p.task_calls or used_in + count.tokens > p.task_input:
                stop = "root task attempt/input limit; a new session cannot reset this"
            elif used_out + output_bound > p.task_output:
                stop = "root task output limit"
            if stop:
                if t["status"] == "RUNNING":
                    c.execute("UPDATE tasks SET status='WAITING_BUDGET' WHERE id=?", (task,))
            else:
                c.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,'IN_FLIGHT',NULL,NULL,?)",
                          (request_id, task, t["segment"], ref["sha256"], count.tokens,
                           output_bound, count.method, self.clock()))
        if stop:
            raise BudgetStop(stop)
        return request_id

    def settle(self, request_id: str, usage: Usage | None, *, error: str = "") -> None:
        """Unknown usage retains the FULL reservation. Never assume a failed send was free."""
        encoded = canonical(asdict(usage)).decode() if usage else None
        breach = False
        with self.transaction() as c:
            r = c.execute("SELECT * FROM attempts WHERE id=?", (request_id,)).fetchone()
            if r is None:
                raise IntegrityError("unknown attempt")
            if r["state"] != "IN_FLIGHT":
                if r["usage"] == encoded and r["error"] == error:
                    return
                raise IntegrityError("conflicting attempt settlement")
            breach = usage is not None and (usage.prompt > r["input_bound"] or
                                            usage.output > r["output_bound"])
            state = "ERROR" if error else ("MEASURED" if usage else "UNKNOWN_USAGE")
            c.execute("UPDATE attempts SET state=?,usage=?,error=? WHERE id=?",
                      (state, encoded, error, request_id))
            if breach:
                c.execute("UPDATE tasks SET status='COUNTER_BREACH' WHERE id=?", (r["task"],))
        if breach:
            raise IntegrityError("certified bound violated: stop rollout and recalibrate counter")

    def checkpoint(self, task: str, state: Mapping[str, Any], *, next_segment: bool = False) -> str:
        self._validate_checkpoint(task, state)
        ref = self.artifacts.put_json(state)
        with self.transaction() as c:
            t = c.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None:
                raise IntegrityError("unknown task")
            old = json.loads(self.artifacts.read(t["checkpoint"]))
            if old["constraints"] != state["constraints"] or old["goal"] != state["goal"]:
                raise IntegrityError("checkpoint cannot silently rewrite goal/constraints")
            if c.execute("SELECT 1 FROM attempts WHERE task=? AND state='IN_FLIGHT'", (task,)).fetchone():
                raise IntegrityError("checkpoint while provider attempt is unresolved")
            segment = t["segment"]
            if next_segment:
                p = Policy(**json.loads(t["policy"]))
                if t["status"] not in ("RUNNING", "WAITING_BUDGET"):
                    raise BudgetStop("task state does not allow continuation")
                if segment + 1 >= p.max_segments:
                    raise BudgetStop("maximum segments reached")
                if not state["next_actions"]:
                    raise IntegrityError("continuation must contain concrete next actions")
                segment += 1
            c.execute("UPDATE tasks SET checkpoint=?,segment=?,status=? WHERE id=?",
                      (ref["sha256"], segment, "RUNNING" if next_segment else t["status"], task))
        return ref["sha256"]

    def approve_extension(self, task: str, policy: Policy, *, approval_id: str,
                          expected_policy_sha: str, approved_by: str, reason: str) -> None:
        """Trusted operator control plane ONLY; never expose this as an agent tool.

        Caller authenticates authorization. CAS + an immutable approval audit keep
        the same task/attempt ledger; an extension is not a new zero-cost task.
        Counter integrity failures cannot be overridden by budget approval.
        """
        if not all(isinstance(v, str) and v.strip() for v in
                   (approval_id, expected_policy_sha, approved_by, reason)):
            raise IntegrityError("authenticated operator approval metadata required")
        encoded = canonical(asdict(policy)).decode()
        with self.transaction() as c:
            previous = c.execute("SELECT * FROM budget_approvals WHERE id=?", (approval_id,)).fetchone()
            if previous:
                if (previous["task"], previous["new_policy"], previous["approved_by"], previous["reason"],
                        digest(json.loads(previous["previous_policy"]))) != (
                        task, encoded, approved_by, reason, expected_policy_sha):
                    raise IntegrityError("conflicting budget approval identity")
                return
            t = c.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None or t["status"] not in ("RUNNING", "WAITING_BUDGET"):
                raise IntegrityError("task does not permit budget extension")
            old = json.loads(t["policy"])
            if digest(old) != expected_policy_sha:
                raise IntegrityError("budget policy CAS conflict")
            new = asdict(policy)
            if any(new[k] < old[k] for k in old) or new == old:
                raise IntegrityError("extension must increase limits, never reset or shrink them")
            if c.execute("SELECT 1 FROM attempts WHERE task=? AND state='IN_FLIGHT'", (task,)).fetchone():
                raise IntegrityError("reconcile provider attempt before extending")
            c.execute("INSERT INTO budget_approvals VALUES(?,?,?,?,?,?,?)",
                      (approval_id, task, t["policy"], encoded, approved_by, reason, self.clock()))
            c.execute("UPDATE tasks SET policy=?,status='RUNNING' WHERE id=?", (encoded, task))

    def inspect(self, task: str) -> dict[str, Any]:
        with self.connection() as c:
            t = c.execute("SELECT * FROM tasks WHERE id=?", (task,)).fetchone()
            if t is None:
                raise IntegrityError("unknown task")
            return {"task": dict(t), "attempts": [dict(r) for r in
                    c.execute("SELECT * FROM attempts WHERE task=? ORDER BY created,id", (task,))]}
