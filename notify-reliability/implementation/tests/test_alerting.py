import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wx_outbox_alert", ROOT / "ops" / "wx_outbox_alert.py")
alert = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(alert)


class AlertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "alerts"
        self.env = mock.patch.dict(os.environ, {
            "HERMES_HOME": str(Path(self.temp.name) / "home"),
            "WX_ALERT_SPOOL": str(self.root),
            "WX_ALERT_HOST_ID": "host-fixture",
            "WX_ACCOUNT_ID": "account-fixture",
        }, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    @staticmethod
    def unhealthy_paused():
        return {
            "healthy": False,
            "paused": True,
            "clock_anomaly": False,
            "disk_free_bytes": 10 * 1024 * 1024 * 1024,
            "heartbeat_age_seconds": 1,
            "oldest_pending_seconds": 0,
            "counts": {"queued": 2, "blocked": 0},
        }

    @staticmethod
    def healthy():
        return {
            "healthy": True,
            "paused": False,
            "clock_anomaly": False,
            "disk_free_bytes": 10 * 1024 * 1024 * 1024,
            "heartbeat_age_seconds": 1,
            "oldest_pending_seconds": 0,
            "counts": {"queued": 0, "blocked": 0},
        }

    def pending_events(self):
        result = []
        for path in sorted((self.root / "pending").glob("*.json")):
            result.append(json.loads(path.read_text(encoding="utf-8")))
        return sorted(result, key=lambda e: alert.parse_iso(e["observed_at"]))

    def test_open_update_and_two_tick_recovery(self):
        base = 1_800_000_000.0
        with mock.patch.object(alert, "run_health", return_value=(2, self.unhealthy_paused())), \
             mock.patch.object(alert.time, "time", return_value=base):
            self.assertEqual(alert.observe(), 2)
        events = self.pending_events()
        self.assertEqual([e["state"] for e in events], ["OPEN"])
        first_seen = events[0]["first_seen_at"]

        with mock.patch.object(alert, "run_health", return_value=(2, self.unhealthy_paused())), \
             mock.patch.object(alert.time, "time", return_value=base + 300):
            self.assertEqual(alert.observe(), 2)
        self.assertEqual(len(self.pending_events()), 1)

        with mock.patch.object(alert, "run_health", return_value=(2, self.unhealthy_paused())), \
             mock.patch.object(alert.time, "time", return_value=base + 601):
            self.assertEqual(alert.observe(), 2)
        events = self.pending_events()
        self.assertEqual([e["state"] for e in events], ["OPEN", "UPDATE"])
        self.assertEqual(events[1]["first_seen_at"], first_seen)
        self.assertEqual(events[1]["update_seq"], 1)

        with mock.patch.object(alert, "run_health", return_value=(0, self.healthy())), \
             mock.patch.object(alert.time, "time", return_value=base + 620):
            self.assertEqual(alert.observe(), 0)
        self.assertEqual(len(self.pending_events()), 2)

        with mock.patch.object(alert, "run_health", return_value=(0, self.healthy())), \
             mock.patch.object(alert.time, "time", return_value=base + 640):
            self.assertEqual(alert.observe(), 0)
        events = self.pending_events()
        self.assertEqual([e["state"] for e in events], ["OPEN", "UPDATE", "RECOVERED"])
        self.assertEqual(events[-1]["first_seen_at"], first_seen)
        self.assertNotEqual(events[0]["alert_id"], events[-1]["alert_id"])

    def test_spool_history_prevents_duplicate_open_after_state_loss(self):
        base = 1_800_000_000.0
        with mock.patch.object(alert, "run_health", return_value=(2, self.unhealthy_paused())), \
             mock.patch.object(alert.time, "time", return_value=base):
            self.assertEqual(alert.observe(), 2)
        (self.root / "state.json").unlink()
        with mock.patch.object(alert, "run_health", return_value=(2, self.unhealthy_paused())), \
             mock.patch.object(alert.time, "time", return_value=base + 60):
            self.assertEqual(alert.observe(), 2)
        events = self.pending_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["state"], "OPEN")

    def test_failed_push_keeps_event_and_success_archives_same_alert_id(self):
        event = alert.make_event(
            failure_class="watchdog_failed", state="OPEN",
            first_seen_at="2026-09-18T05:00:00+08:00",
            observed_at="2026-09-18T05:00:00+08:00",
            last_healthy_at=None,
            health={"counts": {}, "oldest_pending_seconds": None},
        )
        pending = alert.spool_event(self.root, event)
        with mock.patch.object(alert, "push_event", return_value=False):
            self.assertEqual(alert.drain(), 2)
        self.assertTrue(pending.exists())
        with mock.patch.object(alert, "push_event", return_value=True):
            self.assertEqual(alert.drain(), 0)
        self.assertFalse(pending.exists())
        sent = self.root / "sent" / f"{event['alert_id']}.json"
        self.assertTrue(sent.exists())
        self.assertEqual(json.loads(sent.read_text())["alert_id"], event["alert_id"])

    def test_target_name_is_short_stable_and_contains_no_dedupe_chain(self):
        event = alert.make_event(
            failure_class="queue_stalled", state="UPDATE",
            first_seen_at="2026-09-18T05:00:00+08:00",
            observed_at="2026-09-18T05:10:00+08:00",
            last_healthy_at="2026-09-18T04:59:40+08:00",
            health={"counts": {"queued": 3}, "oldest_pending_seconds": 700},
            update_seq=1,
        )
        path = alert.target_path(event)
        self.assertEqual(path, "chat/to-gpt/2026-09-18T051000+0800-wx-outbox-alert-queue-stalled.md")
        self.assertNotIn(event["dedupe_key"], path)
        self.assertNotIn(event["alert_id"], path)

    def test_heartbeat_failure_never_prints_secret_url(self):
        secret = "https://hc-ping.com/very-secret-token"
        with mock.patch.dict(os.environ, {"HEALTHCHECKS_PING_URL": secret}, clear=False), \
             mock.patch.object(alert.urllib.request, "urlopen", side_effect=urllib.error.URLError(secret)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(alert.heartbeat(), 2)
        self.assertNotIn("very-secret-token", output.getvalue())
        self.assertIn("URLError", output.getvalue())


if __name__ == "__main__":
    unittest.main()
