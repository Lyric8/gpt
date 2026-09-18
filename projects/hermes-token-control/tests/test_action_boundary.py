"""Local Git tests for the Stage-1 action-boundary reconciliation gate."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from hermes_token_control.artifacts import Artifacts
from hermes_token_control.dispatcher import ActionDispatcher
from hermes_token_control.queue import EventQueue
from hermes_token_control.remote_gate import RemoteStateError
from hermes_token_control.source_scan import scan_git_inbox

spec = importlib.util.spec_from_file_location("publish_helper", Path(__file__).parents[1] / "bin/publish.py")
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class ActionBoundaryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin.git"
        self.repo = self.root / "work.git"
        for path in (self.origin, self.repo):
            subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True)
        pub.git(self.repo, "remote", "add", "origin", str(self.origin))
        tree = pub.text(self.repo, "mktree", data=b"")
        self.base = pub.text(
            self.repo, "-c", "user.name=test", "-c", "user.email=test@localhost",
            "commit-tree", tree, data=b"initial\n",
        )
        protocol = {p: b"reviewed protocol" for p in (
            "chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md"
        )}
        protocol["chat/STATUS.md"] = b"# status\n"
        self.head = pub.publish_files(
            self.repo, "chat", self.base, protocol,
            replace_prefix=None, message="protocol and status",
        )
        self.expected = {
            path: pub.text(self.repo, "rev-parse", self.head + ":" + path)
            for path in (
                "chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md"
            )
        }
        self.queue = EventQueue(self.root / "events.sqlite3", Artifacts(self.root / "artifacts"))
        self.dispatcher = ActionDispatcher(
            self.repo, self.queue, expected_protocol=self.expected, owner="test-dispatcher"
        )

    def tearDown(self):
        self.temp.cleanup()

    def put(self, files: dict[str, bytes]) -> None:
        self.head = pub.publish_files(
            self.repo, "chat", self.head, files, replace_prefix=None, message="test state"
        )

    def source(self, *, action_required: str = "true", name: str = "request") -> tuple[str, str]:
        path = f"chat/to-hermes/2026-09-18T130000+0800-{name}.md"
        self.put({path: (
            "时间：2026-09-18T13:00:00+08:00　作者：ChatGPT\n"
            f"action_required: {action_required}\n"
            "reply_required: true\n"
            "body\n"
        ).encode()})
        sha = pub.text(self.repo, "rev-parse", self.head + ":" + path)
        scan = scan_git_inbox(self.repo, self.queue, expected_protocol=self.expected)
        self.assertEqual(scan["provider_calls"], 0)
        return path, sha

    def completion(self, path: str, sha: str, *, status: str = "resolved") -> None:
        message_id = Path(path).stem + "--" + sha
        body = {
            "protocol_version": 3,
            "direction": "to-hermes",
            "message_id": message_id,
            "message_path": path,
            "message_blob_sha": sha,
            "completed_at": "2026-09-18T13:01:00+08:00",
            "status": status,
            "evidence": "local-test",
        }
        self.put({
            "chat/completed/to-hermes/2026-09-18T130100+0800-completed-request.json":
                json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
        })

    def state_for(self, path: str, sha: str) -> tuple[str, int]:
        with self.queue.tx() as c:
            row = c.execute(
                "SELECT state,attempts FROM events WHERE item_key=? AND version=?", (path, sha)
            ).fetchone()
            self.assertIsNotNone(row)
            return row["state"], row["attempts"]

    def test_remote_completion_before_local_claim_is_reconciled_without_attempt(self):
        path, sha = self.source()
        self.completion(path, sha)
        self.assertIsNone(self.dispatcher.claim_next_actionable())
        self.assertEqual(self.state_for(path, sha), ("REMOTE_COMPLETED", 0))

    def test_explicit_non_request_is_reconciled_without_claim(self):
        path, sha = self.source(action_required="false", name="notice")
        self.assertIsNone(self.dispatcher.claim_next_actionable())
        self.assertEqual(self.state_for(path, sha), ("NON_REQUEST", 0))

    def test_actionable_event_requires_fresh_permit_at_each_boundary(self):
        path, sha = self.source()
        ticket = self.dispatcher.claim_next_actionable()
        self.assertIsNotNone(ticket)
        self.assertEqual(self.state_for(path, sha), ("RUNNING", 1))
        permit = self.dispatcher.permit(ticket, "remote-message-claim")
        self.assertIsNotNone(permit)
        self.assertEqual(permit.source_path, path)
        self.assertEqual(permit.source_blob_sha, sha)
        second = self.dispatcher.permit(ticket, "model-request")
        self.assertIsNotNone(second)
        self.assertEqual(second.source_message_id, Path(path).stem + "--" + sha)

    def test_remote_completion_after_local_claim_stops_before_next_boundary(self):
        path, sha = self.source()
        ticket = self.dispatcher.claim_next_actionable()
        self.assertIsNotNone(ticket)
        self.completion(path, sha)
        self.assertIsNone(self.dispatcher.permit(ticket, "model-request"))
        self.assertEqual(self.state_for(path, sha), ("REMOTE_COMPLETED", 1))

    def test_terminal_status_without_completion_is_ambiguous_and_fail_closed(self):
        path, sha = self.source()
        line = (
            "| 2026-09-18T13:01:00+08:00 | → Hermes | "
            f"to-hermes/{Path(path).name} | {sha[:12]} | ✅ 已解决 | premature |\n"
        )
        self.put({"chat/STATUS.md": ("# status\n" + line).encode()})
        with self.assertRaises(RemoteStateError):
            self.dispatcher.claim_next_actionable()
        self.assertEqual(self.state_for(path, sha), ("PENDING", 0))

    def test_protocol_drift_before_boundary_releases_and_refunds_local_claim(self):
        path, sha = self.source()
        ticket = self.dispatcher.claim_next_actionable()
        self.assertIsNotNone(ticket)
        self.put({"chat/README.md": b"changed protocol"})
        with self.assertRaises(RemoteStateError):
            self.dispatcher.permit(ticket, "business-write")
        self.assertEqual(self.state_for(path, sha), ("PENDING", 0))

    def test_source_blob_replacement_is_not_authorized_by_stale_ticket(self):
        path, sha = self.source()
        ticket = self.dispatcher.claim_next_actionable()
        self.assertIsNotNone(ticket)
        self.put({path: (
            "时间：2026-09-18T13:00:00+08:00　作者：ChatGPT\n"
            "action_required: true\nreply_required: true\nchanged body\n"
        ).encode()})
        with self.assertRaises(RemoteStateError):
            self.dispatcher.permit(ticket, "business-write")
        self.assertEqual(self.state_for(path, sha), ("PENDING", 0))


if __name__ == "__main__":
    unittest.main()
