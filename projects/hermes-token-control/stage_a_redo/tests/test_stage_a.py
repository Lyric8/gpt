from __future__ import annotations

import copy
import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from stage_a_redo.accounting import COUNTERS, KEY, delta, snapshot
from stage_a_redo.context import Checkpoint, Policy, Prepared, archive_result, closed_turn, dispatch, prepare
from stage_a_redo.probes import CHECKS, PROTOCOL_PATHS, evaluate, observed_call, scan
from stage_a_redo.projection import projection
from stage_a_redo.storage import Journal, Store, encode, git_blob, sha256


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.now = 1000.0
        self.journal = Journal(self.root / "state", clock=lambda: self.now)

    def count(self, table):
        with self.journal.connect() as db:
            return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def observation(self, job="sender", healthy=True, work=False):
        return {"job": job, "observed_at": self.now, "instance": "test-instance",
                "revision": "source-v1", "assertions": {key: healthy for key in CHECKS[job]}, "work": work}


class StorageTests(Fixture):
    def test_archive_round_trip(self):
        data = b"full evidence\0\n"
        reference = self.journal.store.put(data)
        self.assertEqual(self.journal.store.get(reference["sha256"]), data)

    def test_corrupted_archive_detected(self):
        ref = self.journal.store.put(b"data")
        (self.journal.store.root / ref["sha256"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            self.journal.store.get(ref["sha256"])

    def test_attempt_accounting_root_survives_segments(self):
        for segment in ("one", "two"):
            self.journal.record_attempt(attempt_id=segment, root_task_id="root", session_id="session", segment_id=segment, phase="attempt", usage={})
        self.assertEqual(self.count("attempt_records"), 2)
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(DISTINCT root_task_id) FROM attempt_records").fetchone()[0], 1)

    def test_attempt_reuse_is_not_double_counted(self):
        kwargs = dict(attempt_id="one", root_task_id="root", session_id="session", segment_id="one", phase="attempt", usage={})
        self.journal.record_attempt(**kwargs)
        self.journal.record_attempt(**kwargs)
        self.assertEqual(self.count("attempt_records"), 1)

    def test_completed_requires_external_verification(self):
        content = b"a source"
        ref = self.journal.store.put(content)
        event = {"source_path": "a.md", "blob_sha": git_blob(content), "artifact": ref["sha256"], "kind": "test"}
        self.journal.reconcile([event], job="test")
        identity = sha256(encode([event["source_path"], event["blob_sha"]]))
        proof = {"source_path": event["source_path"], "blob_sha": event["blob_sha"], "verified": True}
        with self.assertRaises(ValueError):
            self.journal.reconcile_completed(identity, proof, lambda event, proof: False)
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM events").fetchone()[0], "PENDING")
        self.journal.reconcile_completed(identity, proof, lambda event, proof: True)
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM events").fetchone()[0], "DONE")

    def test_range_validates_address(self):
        with self.assertRaises(ValueError):
            self.journal.store.read_range("../outside", 0, 1)

    def test_read_range(self):
        ref = self.journal.store.put(b"abcdef")
        self.assertEqual(self.journal.store.read_range(ref["sha256"], 2, 2), b"cd")

    def test_reconcile_rollback_bad_blob(self):
        ref = self.journal.store.put(b"data")
        with self.assertRaises(ValueError):
            self.journal.reconcile([{"source_path": "a", "blob_sha": "0" * 40, "artifact": ref["sha256"], "kind": "test"}], job="test")
        self.assertEqual(self.count("events"), 0)

    def test_notice_dedup_and_recovery(self):
        self.journal.notice("x", active=True, category="test")
        self.journal.notice("x", active=True, category="test")
        self.assertEqual(self.count("alerts"), 1)
        self.journal.notice("x", active=False, category="test")
        self.journal.notice("x", active=True, category="test")
        self.assertEqual(self.count("alerts"), 3)

    def test_sender_failure_retained_then_handoff(self):
        self.journal.notice("x", active=True, category="test")
        self.assertEqual(self.journal.drain(Mock(side_effect=OSError)), 0)
        self.now += 60
        sender = Mock(return_value={"durable": True, "receipt_id": "local-sender-1"})
        self.assertEqual(self.journal.drain(sender), 1)
        self.assertEqual(self.journal.drain(sender), 0)
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM alerts").fetchone()[0], "HANDOFF")

    def test_sender_memory_acceptance_is_not_ack(self):
        self.journal.notice("x", active=True, category="test")
        self.assertEqual(self.journal.drain(lambda value: {"durable": False, "receipt_id": "memory"}), 0)
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM alerts").fetchone()[0], "PENDING")


class ProbeTests(Fixture):
    def test_all_seven_probe_kinds_zero_model(self):
        for job in CHECKS:
            with self.subTest(job=job):
                result = evaluate(job, self.observation(job), self.journal)
                self.assertEqual((result["exit_code"], result["model_calls"]), (0, 0))

    def test_actual_failure_reaches_durable_sender(self):
        result = evaluate("sender", self.observation(healthy=False), self.journal)
        self.assertEqual(result["exit_code"], 30)
        self.assertEqual(self.count("events"), 1)
        sender = Mock(return_value={"durable": True, "receipt_id": "sender-confirmation"})
        self.assertEqual(self.journal.drain(sender), 1)
        self.assertEqual(sender.call_args.args[0]["kind"], "health-incident")
        with self.journal.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM events").fetchone()[0], "PENDING")

    def test_duplicate_failure_does_not_spawn_new_work(self):
        evaluate("sender", self.observation(healthy=False), self.journal)
        self.now += 1
        result = evaluate("sender", self.observation(healthy=False), self.journal)
        self.assertEqual(result["new_events"], 0)
        self.assertEqual(self.count("alerts"), 1)

    def test_recovered_same_failure_is_new_episode(self):
        evaluate("sender", self.observation(healthy=False), self.journal)
        self.now += 1
        evaluate("sender", self.observation(), self.journal)
        self.now += 1
        result = evaluate("sender", self.observation(healthy=False), self.journal)
        self.assertEqual(result["new_events"], 1)
        self.assertEqual(self.count("events"), 2)

    def test_pending_work_not_hidden_by_healthy_probe(self):
        evaluate("sender", self.observation(work=True), self.journal)
        self.now += 1
        self.assertEqual(evaluate("sender", self.observation(), self.journal)["exit_code"], 10)

    def test_stale_observation_is_error_not_healthy(self):
        observation = self.observation()
        self.now += 100
        result = observed_call("sender", lambda: evaluate("sender", observation, self.journal), self.journal)
        self.assertEqual(result["exit_code"], 20)
        self.assertEqual(self.count("events"), 0)

    def test_replayed_timestamp_is_error(self):
        observation = self.observation()
        evaluate("sender", observation, self.journal)
        self.assertEqual(observed_call("sender", lambda: evaluate("sender", observation, self.journal), self.journal)["exit_code"], 20)

    def test_missing_assertion_is_drift(self):
        observation = self.observation()
        observation["assertions"].pop("service_healthy")
        result = observed_call("sender", lambda: evaluate("sender", observation, self.journal), self.journal)
        self.assertEqual(result["exit_code"], 21)
        self.assertEqual(self.count("observations"), 0)

    def test_timeout_is_error_and_durable_alert(self):
        action = Mock(side_effect=subprocess.TimeoutExpired("safe-test", 1))
        self.assertEqual(observed_call("inbox", action, self.journal)["exit_code"], 20)
        self.assertEqual(self.count("alerts"), 1)

    def test_alert_failure_is_explicit_partial_not_no_change(self):
        with patch.object(self.journal, "notice", side_effect=OSError):
            result = evaluate("sender", self.observation(healthy=False), self.journal)
        self.assertEqual(result["exit_code"], 31)
        self.assertTrue(result["telemetry_degraded"])
        self.assertEqual(self.count("events"), 1)


class GitTests(Fixture):
    def setUp(self):
        super().setUp()
        self.work = self.root / "git-work"
        self.work.mkdir()
        self.run_git("init", "-b", "chat")
        self.run_git("config", "user.email", "test@example.invalid")
        self.run_git("config", "user.name", "local-test")
        self.approved = {}
        for path in PROTOCOL_PATHS:
            target = self.work / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("approved protocol " + path)
            self.approved[path] = git_blob(target.read_bytes())
        self.source = self.work / "chat/to-hermes/2026-09-18THHMMSS+0800-request.md"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("source one")
        self.commit()
        self.bare = self.root / "cache.git"
        subprocess.run(["git", "init", "--bare", str(self.bare)], check=True, capture_output=True)
        subprocess.run(["git", "--git-dir=" + str(self.bare), "remote", "add", "origin", str(self.work)], check=True)

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, capture_output=True, check=True).stdout

    def commit(self):
        self.run_git("add", "--all")
        self.run_git("commit", "-m", "local test")

    def scan(self):
        return observed_call("inbox", lambda: scan(self.bare, self.journal, self.approved), self.journal)

    def test_initial_source_and_same_head_pending(self):
        self.assertEqual(self.scan()["new_events"], 1)
        again = self.scan()
        self.assertEqual((again["new_events"], again["exit_code"]), (0, 10))

    def test_own_receipt_commit_not_a_source_event(self):
        first = self.scan()
        (self.work / "chat/STATUS.md").write_text("receipt written")
        self.commit()
        result = self.scan()
        self.assertNotEqual(first["snapshot_commit"], result["snapshot_commit"])
        self.assertEqual(result["new_events"], 0)

    def test_same_path_new_blob(self):
        self.scan()
        self.source.write_text("source two")
        self.commit()
        self.assertEqual(self.scan()["new_events"], 1)
        self.assertEqual(self.count("events"), 2)

    def test_no_new_work_only_after_reconciliation(self):
        self.scan()
        # Test-only state fixture; production completion requires remote proof.
        with self.journal.transaction() as db:
            db.execute("UPDATE events SET state='DONE'")
        self.assertEqual(self.scan()["exit_code"], 0)

    def test_same_head_due_retry(self):
        self.scan()
        with self.journal.transaction() as db:
            db.execute("UPDATE events SET available=?", (self.now + 60,))
        self.assertEqual(self.scan()["exit_code"], 0)
        self.now += 61
        self.assertEqual(self.scan()["exit_code"], 10)

    def test_protocol_drift_cannot_advance_seen(self):
        self.scan()
        (self.work / "chat/README.md").write_text("new unapproved protocol")
        self.source.write_text("not yet accepted")
        self.commit()
        self.assertEqual(self.scan()["exit_code"], 21)
        self.assertEqual(self.count("events"), 1)

    def test_fetch_failure_preserves_pending(self):
        self.scan()
        subprocess.run(["git", "--git-dir=" + str(self.bare), "remote", "set-url", "origin", str(self.root / "absent")], check=True)
        self.assertEqual(self.scan()["exit_code"], 20)
        self.assertEqual(self.count("events"), 1)

    def test_long_filename_no_checkout(self):
        relative = "chat/to-hermes/" + "x" * 280 + ".md"
        blob = self.run_git("hash-object", "-w", str(self.source)).decode().strip()
        self.run_git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + relative)
        self.run_git("commit", "-m", "long filename tree only")
        self.assertEqual(self.scan()["new_events"], 2)


class ContextTests(Fixture):
    def payload(self):
        messages = [{"role": "system", "content": "immutable policy"}]
        for n in range(6):
            messages.extend([{"role": "user", "content": "requirement-" + str(n)},
                             {"role": "assistant", "content": "verified result " + str(n) + " " + "x" * 1000}])
        return {"model": "local-test-only", "messages": messages, "tools": [{"type": "function", "function": {"name": "read"}}]}

    def counter(self, value):
        # Test-only deterministic size measure, never represented as tokenizer.
        return len(encode(value))

    def test_huge_context_sent_without_budget_gate(self):
        payload = self.payload()
        sender = Mock(return_value="ok")
        prep = lambda value: prepare(value, store=self.journal.store, counter=lambda _: 10**9)
        self.assertEqual(dispatch(sender, payload, prepare_call=prep, audit=lambda _: None, journal=self.journal), "ok")
        sender.assert_called_once_with(payload)

    def test_prepare_failure_still_sends_original(self):
        payload = self.payload()
        sender = Mock(return_value="ok")
        dispatch(sender, payload, prepare_call=Mock(side_effect=OSError), audit=lambda _: None, journal=self.journal)
        sender.assert_called_once_with(payload)

    def test_mutating_broken_preparer_cannot_corrupt_original(self):
        payload = self.payload()
        def broken(value):
            value["messages"].clear()
            raise RuntimeError()
        sender = Mock()
        dispatch(sender, payload, prepare_call=broken, audit=lambda _: None, journal=self.journal)
        sender.assert_called_once_with(payload)
        self.assertGreater(len(payload["messages"]), 0)

    def test_ledger_and_alert_failure_still_send(self):
        payload = self.payload()
        sender = Mock(return_value="ok")
        with patch.object(self.journal, "notice", side_effect=OSError):
            self.assertEqual(dispatch(sender, payload, prepare_call=lambda value: Prepared(value, (), None, False), audit=Mock(side_effect=sqlite3.OperationalError), journal=self.journal), "ok")
        sender.assert_called_once_with(payload)

    def test_real_provider_failure_is_not_swallowed_or_retried(self):
        sender = Mock(side_effect=TimeoutError("provider"))
        with self.assertRaises(TimeoutError):
            dispatch(sender, self.payload(), prepare_call=lambda value: Prepared(value, (), None, False), audit=lambda _: None)
        self.assertEqual(sender.call_count, 1)

    def test_counter_failure_passes_original(self):
        payload = self.payload()
        result = prepare(payload, store=self.journal.store, counter=Mock(side_effect=RuntimeError))
        self.assertIs(result.payload, payload)
        self.assertIsNone(result.estimated_tokens)

    def test_full_disk_passes_original(self):
        payload = self.payload()
        with patch.object(self.journal.store, "put_json", side_effect=OSError):
            result = prepare(payload, store=self.journal.store, counter=lambda _: 100000)
        self.assertIs(result.payload, payload)

    def test_checkpoint_removes_only_explicit_covered_closed_turn(self):
        payload = self.payload()
        turn = payload["messages"][3:5]
        turn_ref = self.journal.store.put_json(turn)
        capsule = self.journal.store.put_json({"constraints_verbatim": "requirement-1", "verified": "result 1"})
        checkpoint = Checkpoint(capsule["sha256"], frozenset({turn_ref["sha256"]}))
        result = prepare(payload, store=self.journal.store, counter=self.counter,
                         checkpoint=checkpoint, verify_checkpoint=lambda _: True,
                         policy=Policy(1, 100000, 8192, 1))
        messages = result.payload["messages"]
        self.assertNotIn(turn[0], messages)
        self.assertIn(payload["messages"][1], messages)
        self.assertEqual(messages[-2:], payload["messages"][-2:])
        self.assertEqual(result.payload["tools"], payload["tools"])
        self.assertLess(result.estimated_tokens, self.counter(payload))

    def test_untrusted_checkpoint_cannot_remove_turns(self):
        payload = self.payload()
        checkpoint = Checkpoint("0" * 64, frozenset({sha256(encode(payload["messages"][3:5]))}))
        result = prepare(payload, store=self.journal.store, counter=self.counter, checkpoint=checkpoint,
                         verify_checkpoint=lambda _: False, policy=Policy(1, 100000, 8192, 1))
        self.assertEqual(result.payload, payload)

    def test_incomplete_tool_group_not_closed(self):
        turn = [{"role": "user", "content": "do work"}, {"role": "assistant", "tool_calls": [{"id": "c1"}]}]
        self.assertFalse(closed_turn(turn))

    def test_unknown_role_does_not_form_closed_turn(self):
        turn = [{"role": "user", "content": "request"},
                {"role": "provider_extension", "content": "opaque state"},
                {"role": "assistant", "content": "result"}]
        self.assertFalse(closed_turn(turn))

    def test_signed_message_extension_preserves_entire_payload(self):
        payload = self.payload()
        payload["messages"][4]["reasoning_details"] = [{"type": "reasoning.encrypted", "data": "test-only-opaque-state"}]
        turn_ref = self.journal.store.put_json(payload["messages"][3:5])
        capsule = self.journal.store.put_json({"verified": "summary"})
        checkpoint = Checkpoint(capsule["sha256"], frozenset({turn_ref["sha256"]}))
        result = prepare(payload, store=self.journal.store, counter=self.counter,
                         checkpoint=checkpoint, verify_checkpoint=lambda _: True,
                         policy=Policy(1, 100000, 8192, 1))
        self.assertIs(result.payload, payload)

    def test_multimodal_content_preserves_entire_payload(self):
        payload = self.payload()
        payload["messages"][1]["content"] = [{"type": "text", "text": "image-associated request"}]
        result = prepare(payload, store=self.journal.store, counter=lambda _: 100000)
        self.assertIs(result.payload, payload)

    def test_matching_tool_group_closed(self):
        turn = [{"role": "user", "content": "do work"}, {"role": "assistant", "tool_calls": [{"id": "c1"}]},
                {"role": "tool", "tool_call_id": "c1", "content": "result"}, {"role": "assistant", "content": "finished"}]
        self.assertTrue(closed_turn(turn))

    def test_tool_failure_manifest_keeps_failure_and_exact_bytes(self):
        text = "failed test output\n" * 2000
        result = archive_result(text, {"status": "FAILED", "exit_code": 1, "failed_ids": ["T42"]}, self.journal.store)
        manifest = json.loads(result)
        self.assertEqual((manifest["status"], manifest["exit_code"], manifest["failed_ids"]), ("FAILED", 1, ["T42"]))
        self.assertEqual(self.journal.store.get(manifest["sha256"]), text.encode())

    def test_unsupported_payload_passed_without_conversion(self):
        payload = {"input": [{"type": "reasoning", "signature": "test-signature"}]}
        result = prepare(payload, store=self.journal.store, counter=lambda _: 100000)
        self.assertIs(result.payload, payload)


class AccountingTests(Fixture):
    def make_db(self):
        path = self.root / "usage.db"
        db = sqlite3.connect(path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE session_model_usage(" + ",".join([name + " TEXT" for name in KEY] + [name + " INTEGER" for name in COUNTERS]) + ")")
        values = ["session", "model", "provider", "https://example.invalid", "mode", "task", 1, 10, 100, 0, 5, 2]
        db.execute("INSERT INTO session_model_usage VALUES(" + ",".join("?" for _ in values) + ")", values)
        db.commit()
        self.addCleanup(db.close)
        return path, db

    def test_gross_without_double_counting_reasoning(self):
        path, _ = self.make_db()
        result = snapshot(path)
        self.assertEqual(result["totals"]["gross_tokens"], 115)

    def test_live_wal_snapshot_delta(self):
        path, db = self.make_db()
        before = snapshot(path)
        db.execute("UPDATE session_model_usage SET api_call_count=2,input_tokens=20,cache_read_tokens=110,output_tokens=8")
        db.commit()
        result = delta(before, snapshot(path))
        self.assertEqual(result["totals"]["gross_tokens"], 23)
        self.assertEqual(result["totals"]["api_call_count"], 1)

    def test_counter_reset_rejected(self):
        path, db = self.make_db()
        before = snapshot(path)
        db.execute("UPDATE session_model_usage SET input_tokens=0")
        db.commit()
        with self.assertRaises(ValueError):
            delta(before, snapshot(path))

    def test_disappeared_row_rejected(self):
        path, db = self.make_db()
        before = snapshot(path)
        db.execute("DELETE FROM session_model_usage")
        db.commit()
        with self.assertRaises(ValueError):
            delta(before, snapshot(path))

    def test_url_and_task_not_exported(self):
        path, _ = self.make_db()
        text = json.dumps(snapshot(path))
        self.assertNotIn("https://example.invalid", text)
        self.assertNotIn('"task":', text)

    def test_scenarios_are_conditional(self):
        result = projection()
        self.assertEqual(result["target"], 95060000)
        self.assertEqual(result["scenarios"]["conservative_near_boundary"]["gross"], 94624000)
        self.assertFalse(result["scenarios"]["stress_not_fivefold"]["fivefold"])


if __name__ == "__main__":
    unittest.main()
