import importlib.util
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "chat_push_path_file_adapter",
    ROOT / "ops" / "chat_push_path_file_adapter.py",
)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class ChatPushAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        (self.repo / "chat" / "to-gpt").mkdir(parents=True)
        self.backend = base / "chat-push.sh"
        self.backend.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.payload = base / "payload.md"
        self.payload.write_bytes(b"alert payload\n")
        self.env = mock.patch.dict(os.environ, {
            "CHAT_REPO_ROOT": str(self.repo),
            "CHAT_PUSH_BACKEND": str(self.backend),
            "CHAT_PUSH_REMOTE": "origin",
            "CHAT_PUSH_BRANCH": "chat",
        }, clear=False)
        self.env.start()
        self.target = "chat/to-gpt/2026-09-18T060000+0800-wx-outbox-alert-watchdog-failed.md"

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def completed(returncode=0, stdout=None):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout)

    def test_success_requires_exact_remote_payload_after_backend_returns_zero(self):
        results = [
            self.completed(stdout="chat\n"),
            self.completed(),
            self.completed(),
            self.completed(stdout=self.payload.read_bytes()),
        ]
        with mock.patch.object(adapter.subprocess, "run", side_effect=results) as run:
            self.assertEqual(adapter.deliver(self.target, str(self.payload)), adapter.RC_OK)

        destination = self.repo / self.target
        self.assertEqual(destination.read_bytes(), self.payload.read_bytes())
        backend_argv = run.call_args_list[1].args[0]
        self.assertEqual(backend_argv[0], str(self.backend))
        self.assertEqual(len(backend_argv), 2)
        self.assertTrue(backend_argv[1].startswith("chat: deliver "))
        self.assertNotIn(str(self.payload), backend_argv)
        self.assertNotEqual(backend_argv[1], self.target)

    def test_backend_zero_without_remote_file_is_not_success(self):
        results = [
            self.completed(stdout="chat\n"),
            self.completed(),
            self.completed(),
            self.completed(returncode=128, stdout=b""),
        ]
        with mock.patch.object(adapter.subprocess, "run", side_effect=results):
            self.assertEqual(adapter.deliver(self.target, str(self.payload)), adapter.RC_VERIFY)

    def test_backend_failure_is_reported_and_remote_verification_is_not_attempted(self):
        results = [
            self.completed(stdout="chat\n"),
            self.completed(returncode=6),
        ]
        with mock.patch.object(adapter.subprocess, "run", side_effect=results) as run:
            self.assertEqual(adapter.deliver(self.target, str(self.payload)), adapter.RC_BACKEND)
        self.assertEqual(run.call_count, 2)

    def test_existing_different_target_is_fail_closed_and_never_overwritten(self):
        destination = self.repo / self.target
        destination.write_bytes(b"different\n")
        with mock.patch.object(
            adapter.subprocess,
            "run",
            return_value=self.completed(stdout="chat\n"),
        ) as run:
            self.assertEqual(adapter.deliver(self.target, str(self.payload)), adapter.RC_CONFLICT)
        self.assertEqual(destination.read_bytes(), b"different\n")
        self.assertEqual(run.call_count, 1)

    def test_target_is_restricted_to_to_gpt_markdown(self):
        with mock.patch.object(adapter.subprocess, "run") as run:
            self.assertEqual(
                adapter.deliver("chat/to-hermes/not-allowed.md", str(self.payload)),
                adapter.RC_INPUT,
            )
            self.assertEqual(
                adapter.deliver("chat/to-gpt/../../escape.md", str(self.payload)),
                adapter.RC_INPUT,
            )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
