from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hermes_token_control.accounting import COUNTERS, KEY, delta, snapshot, totals
from hermes_token_control.artifacts import Artifacts, canonical, digest
from hermes_token_control.batch import run_read_batch
from hermes_token_control.context import compact_at_boundary, validate_messages
from hermes_token_control.governor import BudgetStop, Governor, IntegrityError, Policy, TokenCount, Usage
from hermes_token_control.provider import GuardedChatCompletions
from hermes_token_control.queue import EventQueue


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Artifacts(self.root / "artifacts")
        self.now = 1000.0
        self.g = Governor(self.root / "budget.db", self.store, lambda: self.now)
        self.state = {"task_id": "T", "goal": "deliver verified code", "constraints": ["no lost work"],
                      "source_versions": {"repo": "a"*40}, "verified": [], "pending": [], "next_actions": ["test"]}
        self.policy = Policy(input_hard=100, calls_per_segment=2, task_calls=3, task_input=300,
                             task_output=40, max_segments=2, output_per_call=10)
        self.g.begin("T", self.state, self.policy)

    def admit(self, tokens=80):
        return self.g.admit("T", {"messages": []}, TokenCount(tokens, "test-fixture", True), 10)

    def settled(self):
        a = self.admit(); self.g.settle(a, Usage(2, 78, 2)); return a


class ArtifactTests(Fixture):
    def test_full_output_retained(self):
        data = ("关键证据"*5000).encode()
        env = self.store.envelope(data)
        self.assertTrue(env["truncated"])
        self.assertEqual(self.store.read(env["artifact"]["sha256"]), data)

    def test_corruption_detected(self):
        ref = self.store.put(b"abc"); Path(ref["path"]).write_bytes(b"bad")
        with self.assertRaises(RuntimeError): self.store.read(ref["sha256"])

    def test_duplicate_artifact(self):
        self.assertEqual(self.store.put(b"abc"), self.store.put(b"abc"))

    def test_invalid_path(self):
        with self.assertRaises(ValueError): self.store.read("../../secrets")

    def test_nan_rejected(self):
        with self.assertRaises(ValueError): self.store.put_json({"a": float("nan")})


class GovernorTests(Fixture):
    def test_uncertified_counter_cannot_send(self):
        with self.assertRaises(BudgetStop):
            self.g.admit("T", {}, TokenCount(1, "chars/4"), 10)
        self.assertEqual(len(self.g.inspect("T")["attempts"]), 0)

    def test_input_limit_before_attempt(self):
        with self.assertRaises(BudgetStop): self.admit(101)
        self.assertEqual(self.g.inspect("T")["task"]["status"], "WAITING_BUDGET")
        self.assertEqual(len(self.g.inspect("T")["attempts"]), 0)

    def test_segment_limit(self):
        self.settled(); self.settled()
        with self.assertRaises(BudgetStop): self.admit()

    def test_root_budget_survives_segment(self):
        self.settled(); self.settled()
        self.g.checkpoint("T", self.state, next_segment=True)
        self.settled()
        with self.assertRaises(BudgetStop): self.admit()

    def test_restart_does_not_reset(self):
        self.settled(); self.settled()
        self.g = Governor(self.root / "budget.db", self.store)
        self.g.begin("T", self.state, self.policy)
        with self.assertRaises(BudgetStop): self.admit()

    def test_unknown_attempt_reserves_input(self):
        a = self.admit(); self.g.settle(a, None, error="TimeoutError")
        self.assertEqual(self.g.inspect("T")["attempts"][0]["input_bound"], 80)
        self.settled()
        with self.assertRaises(BudgetStop): self.admit()

    def test_unresolved_send_blocks_replay(self):
        self.admit()
        with self.assertRaises(IntegrityError): self.admit()
        self.assertEqual(self.g.inspect("T")["task"]["status"], "RUNNING")

    def test_idempotent_settlement(self):
        a = self.settled(); self.g.settle(a, Usage(2, 78, 2))
        self.assertEqual(len(self.g.inspect("T")["attempts"]), 1)

    def test_conflicting_settlement(self):
        a = self.settled()
        with self.assertRaises(IntegrityError): self.g.settle(a, Usage(3, 77, 2))

    def test_counter_breach_freezes(self):
        a = self.admit()
        with self.assertRaises(IntegrityError): self.g.settle(a, Usage(81, 0, 1))
        self.assertEqual(self.g.inspect("T")["task"]["status"], "COUNTER_BREACH")

    def test_checkpoint_preserves_constraints(self):
        s = dict(self.state, constraints=[])
        with self.assertRaises(IntegrityError): self.g.checkpoint("T", s)

    def test_checkpoint_refuses_unresolved_send(self):
        self.admit()
        with self.assertRaises(IntegrityError): self.g.checkpoint("T", self.state, next_segment=True)

    def test_policy_not_replaceable(self):
        with self.assertRaises(IntegrityError): self.g.begin("T", self.state, replace(self.policy, task_calls=100))

    def test_no_unlimited_segments(self):
        self.g.checkpoint("T", self.state, next_segment=True)
        with self.assertRaises(BudgetStop): self.g.checkpoint("T", self.state, next_segment=True)

    def test_concurrent_admission_single_flight(self):
        def attempt(_):
            try: return self.admit()
            except IntegrityError: return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(sum(x is not None for x in outcomes), 1)

    def test_output_reservation_limit(self):
        with self.assertRaises(BudgetStop): self.g.admit("T", {}, TokenCount(1, "test", True), 11)


class UsageTests(unittest.TestCase):
    def test_deepseek_no_double_count(self):
        u = Usage.from_chat_completions({"prompt_tokens": 100, "prompt_cache_hit_tokens": 99,
                "prompt_cache_miss_tokens": 1, "completion_tokens": 20})
        self.assertEqual(u.prompt, 100); self.assertEqual(u.uncached, 1)

    def test_openai_reasoning_is_subset(self):
        u = Usage.from_chat_completions({"prompt_tokens": 100, "prompt_tokens_details": {"cached_tokens": 90},
                "completion_tokens": 20, "completion_tokens_details": {"reasoning_tokens": 15}})
        self.assertEqual(u.prompt+u.output, 120)

    def test_mismatch_rejected(self):
        with self.assertRaises(ValueError): Usage.from_chat_completions({"prompt_tokens": 100,
            "prompt_cache_hit_tokens": 99, "prompt_cache_miss_tokens": 2, "completion_tokens": 20})

    def test_missing_usage_unknown_not_zero(self):
        with self.assertRaises(ValueError): Usage.from_chat_completions({})


class ContextTests(Fixture):
    def test_orphan_tool_rejected(self):
        with self.assertRaises(IntegrityError): validate_messages([{"role": "tool", "tool_call_id": "x"}])

    def test_incomplete_group_rejected(self):
        with self.assertRaises(IntegrityError): validate_messages([{"role": "assistant", "tool_calls": [{"id": "x"}]}])

    def test_parallel_tools_preserved(self):
        validate_messages([{"role": "assistant", "tool_calls": [{"id": "x"}, {"id": "y"}]},
                           {"role": "tool", "tool_call_id": "y"}, {"role": "tool", "tool_call_id": "x"}])

    def compact(self, covered):
        h = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "x"*10000}]
        return compact_at_boundary(prefix=[{"role": "system", "content": "rules"}], history=h,
               current=[{"role": "user", "content": "do current work"}], capsule=self.state,
               covered_turn_hashes={digest(h)} if covered else set(), tools=[], store=self.store,
               counter=lambda p: TokenCount(len(canonical(p)), "test-fixture", True), target_tokens=3000)

    def test_compaction_archives_whole_turn(self):
        r = self.compact(True)
        self.assertEqual(len(r["removed_turn_hashes"]), 1)
        self.assertTrue(self.store.read(r["archive"]["sha256"]))
        self.assertEqual(r["request"]["messages"][-1]["content"], "do current work")

    def test_no_uncovered_history_eviction(self):
        with self.assertRaises(BudgetStop): self.compact(False)


class QueueTests(Fixture):
    def setUp(self):
        super().setUp()
        self.q = EventQueue(self.root / "events.db", self.store, lambda: self.now)
        self.event = {"key": "chat/to-hermes/a.md", "version": "a"*40,
                      "required_checks": ["tests", "readback"]}

    def claim(self):
        self.q.ingest("inbox", None, "head1", [self.event])
        return self.q.claim("worker")

    def receipt(self, claim):
        return {"event_id": claim["id"], "status": "VERIFIED", "source_version": "a"*40,
                "remote_receipt_sha": "b"*40, "remote_completion_sha": "c"*40,
                "checks": {"tests": True, "readback": True}}

    def test_self_write_head_not_new_event(self):
        self.q.ingest("inbox", None, "head1", [self.event])
        self.assertEqual(self.q.ingest("inbox", "head1", "head2", [self.event]), 0)
        self.assertIsNotNone(self.q.claim("one")); self.assertIsNone(self.q.claim("two"))

    def test_scan_error_cannot_advance_cursor(self):
        self.q.ingest("inbox", None, "head1", [self.event])
        with self.assertRaises(IntegrityError): self.q.ingest("inbox", "head1", "head2", [dict(self.event, data="changed")])
        self.assertEqual(self.q.cursor("inbox"), "head1")

    def test_scan_cursor_cas(self):
        self.q.ingest("inbox", None, "head1", [])
        with self.assertRaises(IntegrityError): self.q.ingest("inbox", None, "head2", [])

    def test_lease_takeover_fences_old_owner(self):
        c = self.claim(); self.now += 121
        newer = self.q.claim("new-worker")
        self.assertEqual(newer["epoch"], c["epoch"]+1)
        with self.assertRaises(IntegrityError): self.q.finish_local(c["id"], "worker", c["epoch"], self.receipt(c))

    def test_expired_lease_no_completion(self):
        c = self.claim(); self.now += 121
        with self.assertRaises(IntegrityError): self.q.finish_local(c["id"], "worker", c["epoch"], self.receipt(c))

    def test_failed_check_no_completion(self):
        c = self.claim(); r = self.receipt(c); r["checks"]["tests"] = False
        with self.assertRaises(IntegrityError): self.q.finish_local(c["id"], "worker", c["epoch"], r)
        self.assertEqual(self.q.pending_notifications(), [])

    def test_missing_check_no_completion(self):
        c = self.claim(); r = self.receipt(c); del r["checks"]["tests"]
        with self.assertRaises(IntegrityError): self.q.finish_local(c["id"], "worker", c["epoch"], r)

    def test_receipt_source_version_match(self):
        c = self.claim(); r = dict(self.receipt(c), source_version="d"*40)
        with self.assertRaises(IntegrityError): self.q.finish_local(c["id"], "worker", c["epoch"], r)

    def test_completion_and_notification_durable(self):
        c = self.claim(); self.q.finish_local(c["id"], "worker", c["epoch"], self.receipt(c))
        q = EventQueue(self.root / "events.db", self.store, lambda: self.now)
        self.assertEqual(len(q.pending_notifications()), 1)
        self.assertIsNone(q.claim("another"))
        q.acknowledge_notification(c["id"], "sender-ack")
        self.assertEqual(q.pending_notifications(), [])

    def test_notification_cannot_disappear_without_ack(self):
        c = self.claim(); self.q.finish_local(c["id"], "worker", c["epoch"], self.receipt(c))
        with self.assertRaises(IntegrityError): self.q.acknowledge_notification(c["id"], "")
        self.assertEqual(len(self.q.pending_notifications()), 1)

    def test_deferred_work_visible_without_new_scan(self):
        c = self.claim(); self.q.defer(c["id"], "worker", c["epoch"], delay=60, reason="rate-limited")
        self.assertIsNone(self.q.claim("new")); self.now += 61
        self.assertIsNotNone(self.q.claim("new"))

    def test_retry_exhaustion_blocks_not_done(self):
        c = self.claim(); self.now += 121
        self.assertIsNone(self.q.claim("new", max_attempts=1))
        with self.q.tx() as db:
            self.assertEqual(db.execute("SELECT state FROM events").fetchone()[0], "BLOCKED")


class BatchTests(Fixture):
    def spec(self, key, code, **kwargs):
        return {"id": key, "argv": [sys.executable, "-c", code], "independent_read_only": True, **kwargs}

    def test_batch_all_results_and_failure(self):
        result = run_read_batch([self.spec("pass", "print('ok')"), self.spec("fail", "raise SystemExit(3)")], self.store, cwd=self.root)
        self.assertFalse(result["success"]); self.assertEqual(result["observed_count"], 2)
        self.assertEqual(result["failed_ids"], ["fail"])

    def test_large_evidence_not_in_model_summary(self):
        result = run_read_batch([self.spec("large", "print('x'*200000)")], self.store, cwd=self.root)
        self.assertTrue(result["success"]); self.assertLess(len(canonical(result)), 2048)
        data = json.loads(self.store.read(result["manifest"]["sha256"]))
        ref = data["results"][0]["stdout"]["artifact"]
        self.assertEqual(len(self.store.read(ref["sha256"])), 200001)

    def test_timeout_is_incomplete(self):
        r = run_read_batch([self.spec("hang", "import time;time.sleep(10)", timeout_seconds=.1)], self.store, cwd=self.root)
        self.assertFalse(r["success"]); self.assertFalse(r["results"][0]["complete"])

    def test_quota_violation_is_visible(self):
        r = run_read_batch([self.spec("big", "print('x'*10000)", max_output_bytes=100)], self.store, cwd=self.root)
        self.assertFalse(r["success"])

    def test_write_not_accepted_as_read_batch(self):
        s = self.spec("write", "print('ok')"); s["independent_read_only"] = False
        with self.assertRaises(ValueError): run_read_batch([s], self.store, cwd=self.root)


class ExtensionTests(Fixture):
    def test_audited_extension_preserves_attempts_and_is_idempotent(self):
        attempt = self.g.admit("T", {}, TokenCount(80, "test", True), 10)
        self.g.settle(attempt, Usage(80, 0, 2))
        policy = replace(self.policy, task_calls=5, task_input=500)
        params = dict(approval_id="operator-123", expected_policy_sha=digest(json.loads(self.g.inspect("T")["task"]["policy"])),
                      approved_by="authenticated-operator", reason="incident budget increase")
        self.g.approve_extension("T", policy, **params)
        self.g.approve_extension("T", policy, **params)
        self.assertEqual(len(self.g.inspect("T")["attempts"]), 1)
        with self.g.connection() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM budget_approvals").fetchone()[0], 1)

    def test_extension_requires_cas_and_cannot_shrink(self):
        args = dict(approval_id="A", expected_policy_sha="incorrect", approved_by="operator", reason="explicit")
        with self.assertRaises(IntegrityError): self.g.approve_extension("T", replace(self.policy, task_calls=5), **args)
        args["expected_policy_sha"] = digest(json.loads(self.g.inspect("T")["task"]["policy"]))
        with self.assertRaises(IntegrityError): self.g.approve_extension("T", replace(self.policy, task_input=1), **args)

    def test_extension_does_not_override_counter_breach(self):
        attempt = self.g.admit("T", {}, TokenCount(10, "test", True), 10)
        with self.assertRaises(IntegrityError): self.g.settle(attempt, Usage(11, 0, 2))
        with self.assertRaises(IntegrityError):
            self.g.approve_extension("T", replace(self.policy, task_calls=5), approval_id="A",
                expected_policy_sha=digest(json.loads(self.g.inspect("T")["task"]["policy"])),
                approved_by="operator", reason="cannot repair an invalid tokenizer")


class ProviderTests(Fixture):
    def client(self, response=None, error=None, retries=0):
        def send(**kwargs):
            if error: raise error
            return response
        return SimpleNamespace(max_retries=retries, chat=SimpleNamespace(completions=SimpleNamespace(create=send)))

    def gate(self, client):
        return GuardedChatCompletions(client, self.g, lambda _: TokenCount(80, "test-fixture", True), context_window=1024)

    def test_hidden_sdk_retries_refused(self):
        with self.assertRaises(IntegrityError): self.gate(self.client(retries=2))

    def test_api_failure_counted(self):
        gate = self.gate(self.client(error=TimeoutError()))
        with self.assertRaises(TimeoutError): gate.create(task="T", messages=[], max_tokens=10)
        self.assertEqual(self.g.inspect("T")["attempts"][0]["state"], "ERROR")

    def test_stream_not_silently_bypassed(self):
        with self.assertRaises(IntegrityError): self.gate(self.client()).create(task="T", messages=[], stream=True, max_tokens=10)

    def test_success_recorded(self):
        r = SimpleNamespace(usage={"prompt_tokens": 80, "completion_tokens": 2})
        self.assertIs(self.gate(self.client(response=r)).create(task="T", messages=[], max_tokens=10), r)
        self.assertEqual(self.g.inspect("T")["attempts"][0]["state"], "MEASURED")

    def test_context_window_reserve_checked_before_send(self):
        gate = GuardedChatCompletions(self.client(), self.g,
            lambda _: TokenCount(80, "test-fixture", True), context_window=85)
        with self.assertRaises(IntegrityError): gate.create(task="T", messages=[], max_tokens=10)
        self.assertEqual(self.g.inspect("T")["attempts"], [])

    def test_truncated_generation_not_returned_as_success(self):
        response = SimpleNamespace(usage={"prompt_tokens":80,"completion_tokens":10},
                                   choices=[SimpleNamespace(finish_reason="length")])
        with self.assertRaises(IntegrityError):
            self.gate(self.client(response=response)).create(task="T", messages=[], max_tokens=10)
        self.assertEqual(self.g.inspect("T")["attempts"][0]["state"], "MEASURED")


class AccountingTests(Fixture):
    def seed(self):
        db = self.root / "usage.db"
        c = sqlite3.connect(db)
        c.execute("CREATE TABLE session_model_usage("+",".join(k+" TEXT" for k in KEY)+","+",".join(k+" INTEGER" for k in COUNTERS)+",estimated_cost_usd REAL,actual_cost_usd REAL)")
        values = ["s", "m", "p", "url", "mode", "main", 1, 1, 99, 0, 10, 5, .2, None]
        c.execute("INSERT INTO session_model_usage VALUES("+",".join("?" for _ in values)+")", values)
        c.commit(); c.close(); return db

    def test_snapshot_gross_not_reasoning_double_count(self):
        s = snapshot(self.seed()); self.assertEqual(s["totals"]["gross_tokens"], 110)

    def test_delta_same_rows(self):
        db = self.seed(); before = snapshot(db)
        c = sqlite3.connect(db); c.execute("UPDATE session_model_usage SET input_tokens=3,cache_read_tokens=199,api_call_count=2"); c.commit(); c.close()
        self.assertEqual(delta(before, snapshot(db))["totals"]["prompt_tokens"], 102)

    def test_reset_cannot_fake_saving(self):
        db = self.seed(); before = snapshot(db)
        c = sqlite3.connect(db); c.execute("UPDATE session_model_usage SET input_tokens=0"); c.commit(); c.close()
        with self.assertRaises(IntegrityError): delta(before, snapshot(db))

    def test_missing_rows_fail(self):
        db = self.seed(); before = snapshot(db)
        c = sqlite3.connect(db); c.execute("DELETE FROM session_model_usage"); c.commit(); c.close()
        with self.assertRaises(IntegrityError): delta(before, snapshot(db))


if __name__ == "__main__":
    unittest.main()
