"""Stage-1 no-hard-cap policy and source-identity scanner tests."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from hermes_token_control.artifacts import Artifacts
from hermes_token_control.queue import EventQueue
from hermes_token_control.source_scan import ProtocolDrift, scan_git_inbox
from hermes_token_control.stage1 import Stage1Policy, advise, alert_payload

spec = importlib.util.spec_from_file_location("publish_helper", Path(__file__).parents[1] / "bin/publish.py")
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class Stage1PolicyTests(unittest.TestCase):
    def test_below_threshold_sends_without_alert(self):
        a = advise(input_tokens=47_999, provider_calls_in_segment=4)
        self.assertTrue(a.allow_task)
        self.assertEqual(a.request_action, "SEND")
        self.assertEqual(a.severity, "ok")

    def test_compaction_threshold_is_advisory_not_gate(self):
        a = advise(input_tokens=48_000, provider_calls_in_segment=6)
        self.assertTrue(a.allow_task)
        self.assertEqual(a.request_action, "COMPACT")
        self.assertEqual(a.severity, "warning")

    def test_strong_threshold_segments_but_never_rejects_task(self):
        a = advise(input_tokens=80_000, provider_calls_in_segment=13)
        self.assertTrue(a.allow_task)
        self.assertEqual(a.request_action, "SEGMENT")
        self.assertEqual(a.severity, "strong")

    def test_gross_target_is_alert_only(self):
        p = Stage1Policy(gross_target_tokens=100)
        a = advise(input_tokens=1, provider_calls_in_segment=1, period_gross_tokens=101, policy=p)
        self.assertTrue(a.allow_task)
        self.assertEqual(a.severity, "warning")
        payload = alert_payload(task_id="t", advisory=a, evidence={"snapshot": "abc"})
        self.assertFalse(payload["blocking"])

    def test_invalid_metrics_are_rejected_as_integrity_error_not_budget_stop(self):
        with self.assertRaises(ValueError):
            advise(input_tokens=-1, provider_calls_in_segment=0)


class SourceIdentityScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin, self.repo = self.root / "origin.git", self.root / "work.git"
        for path in (self.origin, self.repo):
            pub.git(path, "init", "--bare")
        pub.git(self.repo, "remote", "add", "origin", str(self.origin))
        tree = pub.text(self.repo, "mktree", data=b"")
        self.head = pub.text(
            self.repo,
            "-c", "user.name=test",
            "-c", "user.email=test@localhost",
            "commit-tree", tree,
            data=b"initial\n",
        )
        self.protocol_files = {
            p: b"approved protocol"
            for p in ("chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md")
        }
        self.head = pub.publish_files(
            self.repo, "chat", self.head, self.protocol_files,
            replace_prefix=None, message="protocol",
        )
        self.expected = {
            p: pub.text(self.repo, "rev-parse", self.head + ":" + p)
            for p in self.protocol_files
        }
        self.queue = EventQueue(self.root / "events.sqlite3", Artifacts(self.root / "artifacts"))

    def tearDown(self):
        self.temp.cleanup()

    def put(self, files):
        self.head = pub.publish_files(
            self.repo, "chat", self.head, files,
            replace_prefix=None, message="next",
        )

    def test_source_identity_is_path_plus_blob_not_head(self):
        self.put({"chat/to-hermes/request.md": b"v1"})
        first = scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)
        self.assertEqual(first["queued"], 1)
        self.assertEqual(first["provider_calls"], 0)
        self.assertEqual(first["identity_rule"], "source_path+source_blob_sha")

        # Change branch HEAD with an unrelated self-write. A HEAD cursor would
        # call this a change; the source-identity scanner must not create work.
        self.put({"chat/STATUS.md": b"self write"})
        second = scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)
        self.assertEqual(second["queued"], 0)
        self.assertEqual(second["provider_calls"], 0)

    def test_new_blob_at_same_source_path_is_new_event(self):
        self.put({"chat/to-hermes/request.md": b"v1"})
        self.assertEqual(scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)["queued"], 1)
        self.put({"chat/to-hermes/request.md": b"v2"})
        self.assertEqual(scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)["queued"], 1)

    def test_protocol_drift_is_visible_failure_and_does_not_mean_no_change(self):
        self.put({"chat/to-hermes/request.md": b"v1"})
        scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)
        self.put({"chat/README.md": b"changed protocol"})
        with self.assertRaises(ProtocolDrift):
            scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)


if __name__ == "__main__":
    unittest.main()
