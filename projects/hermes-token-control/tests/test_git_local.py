"""Real local Git integration, no external network/provider/gateway access."""
from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

from hermes_token_control.artifacts import Artifacts
from hermes_token_control.git_observer import observe
from hermes_token_control.governor import IntegrityError
from hermes_token_control.queue import EventQueue

spec = importlib.util.spec_from_file_location("publish_helper", Path(__file__).parents[1] / "bin/publish.py")
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class LocalGitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.origin, self.repo = self.root / "origin.git", self.root / "work.git"
        for path in (self.origin, self.repo):
            subprocess.run(["git", "init", "--bare", str(path)], check=True, capture_output=True)
        pub.git(self.repo, "remote", "add", "origin", str(self.origin))
        tree = pub.text(self.repo, "mktree", data=b"")
        self.base = pub.text(self.repo, "-c", "user.name=test", "-c", "user.email=test@localhost",
                             "commit-tree", tree, data=b"initial\n")
        self.protocol = {p: b"reviewed protocol" for p in (
            "chat/README.md", "chat/LEASE_PROTOCOL.md", "chat/RESOURCE_LEASE_PROTOCOL.md")}
        self.head = pub.publish_files(self.repo, "chat", self.base, self.protocol,
                                     replace_prefix=None, message="protocol")
        self.expected = {p: pub.text(self.repo, "rev-parse", self.head + ":" + p) for p in self.protocol}
        self.queue = EventQueue(self.root / "events.sqlite3", Artifacts(self.root / "artifacts"))

    def tearDown(self):
        self.temp.cleanup()

    def put(self, files):
        self.head = pub.publish_files(self.repo, "chat", self.head, files,
                                     replace_prefix=None, message="next")

    def test_observer_bootstrap_and_self_writes_do_not_duplicate(self):
        self.put({"chat/to-hermes/request.md": b"real request"})
        first = observe(self.repo, self.queue, expected_protocol=self.expected)
        self.assertEqual(first["queued"], 1); self.assertIs(first["wakeAgent"], False)
        self.put({"chat/STATUS.md": b"own status write"})
        self.assertEqual(observe(self.repo, self.queue, expected_protocol=self.expected)["queued"], 0)
        self.assertEqual(observe(self.repo, self.queue, expected_protocol=self.expected)["status"], "UNCHANGED")

    def test_source_new_blob_is_a_new_event(self):
        self.put({"chat/to-hermes/request.md": b"v1"})
        self.assertEqual(observe(self.repo, self.queue, expected_protocol=self.expected)["queued"], 1)
        self.put({"chat/to-hermes/request.md": b"v2"})
        self.assertEqual(observe(self.repo, self.queue, expected_protocol=self.expected)["queued"], 1)

    def test_protocol_drift_refuses_cursor_advance(self):
        observe(self.repo, self.queue, expected_protocol=self.expected)
        cursor = self.queue.cursor("github:Lyric8/gpt:chat:to-hermes")
        self.put({"chat/README.md": b"new protocol"})
        with self.assertRaises(IntegrityError): observe(self.repo, self.queue, expected_protocol=self.expected)
        self.assertEqual(self.queue.cursor("github:Lyric8/gpt:chat:to-hermes"), cursor)

    def test_publication_does_not_checkout_historical_long_filenames(self):
        long_path = "chat/to-hermes/" + "x" * 278 + ".md"
        self.put({long_path: b"legacy", "chat/to-hermes/short.md": b"modern"})
        self.assertEqual(pub.git(self.repo, "show", self.head + ":" + long_path), b"legacy")
        self.assertEqual(observe(self.repo, self.queue, expected_protocol=self.expected)["queued"], 2)

    def test_replaces_only_designated_source_subtree(self):
        self.put({"projects/token/obsolete.py": b"old", "projects/other/keep.py": b"keep"})
        sha = pub.publish_files(self.repo, "chat", self.head, {"projects/token/new.py": b"new"},
                                replace_prefix="projects/token", message="replace owned subtree")
        paths = pub.git(self.repo, "ls-tree", "-rz", "--name-only", sha).split(b"\0")
        self.assertNotIn(b"projects/token/obsolete.py", paths)
        self.assertIn(b"projects/other/keep.py", paths)
        self.assertIn(b"projects/token/new.py", paths)

    def test_noop_publication_reuses_commit(self):
        sha = pub.publish_files(self.repo, "chat", self.head, self.protocol,
                                replace_prefix=None, message="same")
        self.assertEqual(sha, self.head)

    def test_concurrent_remote_change_rejects_stale_publish(self):
        stale = self.head
        self.put({"chat/to-hermes/winner.md": b"winner"})
        with self.assertRaises(RuntimeError):
            pub.publish_files(self.repo, "chat", stale, {"chat/to-hermes/loser.md": b"loser"},
                               replace_prefix=None, message="stale contender")
        self.assertEqual(pub.remote_sha(self.repo, "chat"), self.head)


if __name__ == "__main__":
    unittest.main()
