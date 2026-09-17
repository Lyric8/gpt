import asyncio
import dataclasses
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gateway.reliable_outbox import (
    AccountLock, DeliveryError, Part, Store, Worker, canonical, digest,
    split_exact, utf16_length, validate_ack, retry_after, run_io,
)
from gateway import reliable_weixin as binding
from gateway.wx_outbox_cli import admit, import_queue, collect_cron


class Clock:
    def __init__(self): self.now = 1000.0
    def __call__(self): return self.now
    def advance(self, n=1000): self.now += n


def reserve(s, key="one", *, ready=True, account="account", profile="default", body="原文", category="reply"):
    return s.reserve(account=account, profile=profile, chat="peer", key=key,
                     raw={"type": "text", "body": body}, session=None, ready=ready, category=category)


def queue(s, key="one", parts=None, **kwargs):
    mid = reserve(s, key, **kwargs)
    s.finish_plan(mid, parts or [Part("text", text="原文")])
    return mid


def crash_after_remote_acceptance(db, lockdir, receipt):
    s = Store(db)
    with AccountLock(Path(lockdir), "account"):
        s.recover("account", "child")
        part = s.claim("account", gap=0)
        with open(receipt, "w") as f:
            json.dump({"accepted_id": part["id"]}, f)
            f.flush(); os.fsync(f.fileno())
        os.kill(os.getpid(), signal.SIGKILL)


def try_lock(lockdir, output):
    try:
        lock = AccountLock(Path(lockdir), "account")
    except BlockingIOError:
        output.put("busy")
    else:
        output.put("acquired")
        lock.close()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.s = Store(self.root/"state.db", clock=self.clock)
    def tearDown(self): self.temp.cleanup()

    def test_idempotency_never_resets_accepted(self):
        mid = queue(self.s)
        part = self.s.claim("account"); self.s.finish(part, None)
        self.assertEqual(mid, reserve(self.s))
        self.s.finish_plan(mid, [Part("text", text="not used")])
        self.assertEqual(self.s.status(mid)["state"], "accepted")
        self.assertEqual(self.s.status(mid)["parts"][0]["attempts"], 1)

    def test_conflicting_key_does_not_overwrite(self):
        mid = reserve(self.s)
        with self.assertRaisesRegex(ValueError, "conflict"):
            reserve(self.s, body="不同正文")
        self.assertEqual(self.s.status(mid)["state"], "preparing")
        with self.s.connect() as c:
            forensic = c.execute("SELECT raw,state FROM wx_outbox_messages WHERE category='conflict'").fetchone()
            self.assertIn("不同正文", forensic[0])
            self.assertEqual(forensic[1], "blocked")
        self.s.resume("account")
        self.assertEqual(self.s.health("account")["counts"].get("blocked"), 1)

    def test_same_body_distinct_events_are_not_deduplicated(self):
        self.assertNotEqual(reserve(self.s, "first"), reserve(self.s, "second"))

    def test_account_profile_isolation(self):
        reserve(self.s)
        with self.assertRaises(ValueError): reserve(self.s, "two", profile="different")
        self.assertNotEqual(reserve(self.s), reserve(self.s, account="other"))

    def test_lossless_unicode_and_whitespace(self):
        text = "  开头\n" + ("🧑🏽‍💻\n    x = 1\t  \n" * 1000) + "尾部  \n"
        pieces = split_exact(text)
        self.assertEqual("".join(pieces), text)
        self.assertTrue(all(utf16_length(p) <= 1800 for p in pieces))
        physical = binding.text_parts("a"*64, text)
        self.assertTrue(all(utf16_length(p.text) < 1950 for p in physical))

    def test_short_multiline_is_one_part(self):
        self.assertEqual(len(binding.text_parts("a"*64, "你好\n已经完成\n请查收")), 1)

    def test_no_send_until_resume_barrier(self):
        mid = queue(self.s, ready=False)
        self.assertIsNone(self.s.claim("account"))
        self.s.activate(mid)
        self.assertIsNotNone(self.s.claim("account"))

    def test_partial_text_then_attachment_failure(self):
        mid = queue(self.s, parts=[Part("text", text="正文"), Part("file", data=b"pdf", filename="r.pdf")])
        one = self.s.claim("account"); self.s.finish(one, None)
        self.clock.advance()
        two = self.s.claim("account"); self.assertEqual(two["seq"], 1)
        self.s.finish(two, DeliveryError("rate", throttle=True), jitter=lambda: 0)
        self.assertEqual(self.s.status(mid)["state"], "queued")
        self.clock.advance()
        retry = self.s.claim("account")
        self.assertEqual(retry["id"], two["id"])
        self.s.finish(retry, None)
        self.assertEqual(self.s.status(mid)["state"], "accepted")
        self.assertEqual(self.s.status(mid)["parts"][0]["attempts"], 1)

    def test_cooldown_is_account_wide_and_survives_reopen(self):
        queue(self.s); queue(self.s, "two")
        p = self.s.claim("account")
        self.s.finish(p, DeliveryError("rate", throttle=True, delay=67), jitter=lambda: 0)
        reopened = Store(self.s.path, clock=self.clock)
        reopened.recover("account", "new")
        self.clock.advance(66)
        self.assertIsNone(reopened.claim("account"))
        self.clock.advance(1)
        self.assertIsNotNone(reopened.claim("account"))

    def test_attempting_recovery_is_ambiguous_and_fenced(self):
        mid = queue(self.s)
        old = self.s.claim("account")
        self.s.recover("account", "new")
        self.clock.advance()
        new = self.s.claim("account")
        self.assertEqual(new["id"], old["id"])
        with self.assertRaisesRegex(RuntimeError, "fenced"): self.s.finish(old, None)
        self.s.finish(new, None)
        self.assertEqual(self.s.status(mid)["parts"][0]["ambiguous"], 1)

    def test_retries_do_not_expire_or_cap(self):
        mid = queue(self.s)
        for _ in range(12):
            p = self.s.claim("account")
            self.assertIsNotNone(p)
            self.s.finish(p, DeliveryError("rate", throttle=True), jitter=lambda: 0)
            self.clock.advance(86400)
        self.assertEqual(self.s.status(mid)["state"], "queued")
        self.s.finish(self.s.claim("account"), None)
        self.assertEqual(self.s.status(mid)["state"], "accepted")

    def test_retention_does_not_delete_700_pending(self):
        for i in range(700): reserve(self.s, str(i))
        mid = queue(self.s, "accepted")
        self.s.finish(self.s.claim("account"), None)
        self.clock.advance(8*86400)
        self.assertEqual(self.s.scrub_accepted_payloads(), 1)
        self.assertEqual(self.s.health("account")["counts"]["preparing"], 700)
        self.assertEqual(reserve(self.s, "accepted"), mid)
        self.assertEqual(self.s.status(mid)["state"], "accepted")

    def test_permanent_auth_pauses_until_explicit_repair(self):
        mid = queue(self.s)
        self.s.finish(self.s.claim("account"), DeliveryError("auth", retry=False, account_pause=True))
        self.clock.advance()
        self.assertIsNone(self.s.claim("account"))
        self.assertEqual(self.s.status(mid)["state"], "blocked")
        self.s.resume("account")
        self.s.finish(self.s.claim("account"), None)
        self.assertEqual(self.s.status(mid)["state"], "accepted")

    def test_notice_coalesces_and_never_recurses(self):
        queue(self.s); queue(self.s, "two")
        self.clock.advance(121)
        self.s.notice("account"); self.s.notice("account")
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM wx_outbox_messages WHERE category='notice'").fetchone()[0], 1)
        self.clock.advance(1000); self.s.notice("account")
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM wx_outbox_messages WHERE category='notice'").fetchone()[0], 1)

    def test_legacy_ownership_transfer_atomic_idempotent(self):
        with self.s.transaction() as c:
            c.execute("CREATE TABLE delivery_obligations (obligation_id TEXT PRIMARY KEY, platform TEXT, adapter_profile TEXT,chat_id TEXT, session_key TEXT,content TEXT,state TEXT,updated_at REAL,last_error TEXT)")
            c.execute("INSERT INTO delivery_obligations VALUES ('legacy','weixin','default','peer','session','report','failed',0,'rate')")
        self.s.import_legacy("account", "default", ["legacy"])
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM delivery_obligations").fetchone()[0], "failed")
        self.s.import_legacy("account", "default", ["legacy"], apply=True)
        self.assertEqual(self.s.import_legacy("account", "default", ["legacy"], apply=True), [])
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM delivery_obligations").fetchone()[0], "outbox_managed")
            mid = c.execute("SELECT id FROM wx_outbox_messages").fetchone()[0]
        self.s.finish_plan(mid, [Part("text", text="legacy")]); self.s.activate(mid)
        self.s.finish(self.s.claim("account"), None)
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM delivery_obligations").fetchone()[0], "delivered")

    def test_process_lock_prevents_second_owner(self):
        ctx = multiprocessing.get_context("spawn")
        output = ctx.Queue()
        with AccountLock(self.root/"locks", "account"):
            child = ctx.Process(target=try_lock, args=(str(self.root/"locks"), output))
            child.start(); child.join(10)
            self.assertEqual(child.exitcode, 0)
            self.assertEqual(output.get(timeout=2), "busy")
        child = ctx.Process(target=try_lock, args=(str(self.root/"locks"), output))
        child.start(); child.join(10)
        self.assertEqual(child.exitcode, 0)
        self.assertEqual(output.get(timeout=2), "acquired")
        output.close()

    def test_real_sigkill_after_provider_receipt_before_local_ack(self):
        # Use real clock so the subprocess and parent have the same time domain.
        s = Store(self.root/"crash.db")
        mid = queue(s)
        ctx = multiprocessing.get_context("spawn")
        receipt = self.root/"remote_receipt.json"
        child = ctx.Process(target=crash_after_remote_acceptance,
                            args=(str(s.path), str(self.root/"locks"), str(receipt)))
        child.start(); child.join(10)
        self.assertEqual(child.exitcode, -signal.SIGKILL)
        self.assertEqual(s.status(mid)["parts"][0]["state"], "sending")
        accepted_id = json.loads(receipt.read_text())["accepted_id"]
        with AccountLock(self.root/"locks", "account"):
            s.recover("account", "new")
            part = s.claim("account", gap=0)
            self.assertEqual(part["id"], accepted_id)
            self.assertEqual(part["ambiguous"], 1)
            s.finish(part, None, gap=0)
        # A non-idempotent receiver could see TWO copies; that is intentional
        # at-least-once semantics, not a false exactly-once assertion.
        self.assertEqual(s.status(mid)["state"], "accepted")

    def test_failed_plan_keeps_raw(self):
        mid = reserve(self.s)
        self.s.block_plan(mid, "missing_attachment")
        with self.s.connect() as c:
            self.assertIn("原文", c.execute("SELECT raw FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()[0])
        self.assertEqual(self.s.status(mid)["state"], "blocked")

    def test_queue_partial_is_not_blindly_replayed(self):
        path = self.root/"20260918T020000-abcdef.txt"
        path.write_text("abc", encoding="utf-8")
        path.with_name(path.name+".part").write_text("1")
        result = import_queue(self.s, self.root, account="account", profile="default", chat="peer")
        self.assertEqual(result[0]["state"], "manual_partial_replay_required")
        result = import_queue(self.s, self.root, account="account", profile="default", chat="peer", accept_partial_duplicates=True)
        self.assertTrue(result[0]["durable"])
        self.assertTrue(path.exists())
        result2 = import_queue(self.s, self.root, account="account", profile="default", chat="peer", accept_partial_duplicates=True)
        self.assertEqual(result[0]["id"], result2[0]["id"])

    def test_admission_never_claims_provider_success(self):
        result = admit(self.s, account="account", profile="default", chat="peer", key="job:1", body="notice")
        self.assertTrue(result["durable"])
        self.assertFalse(result["provider_accepted"])

    def test_sqlite_full_does_not_become_success(self):
        with mock.patch.object(self.s, "_reserve", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError): reserve(self.s)
        self.assertEqual(self.s.health("account")["counts"], {})

    def test_snapshot_is_independent_of_source_and_rejects_symlink(self):
        path = self.root/"x.pdf"; path.write_bytes(b"original")
        data = binding.snapshot(str(path)); path.write_bytes(b"changed")
        self.assertEqual(data, b"original")
        link = self.root/"link.pdf"; link.symlink_to(path)
        with self.assertRaises(OSError): binding.snapshot(str(link))


class ClassificationTests(unittest.TestCase):
    def test_http_429_honors_server_retry_after(self):
        with self.assertRaises(DeliveryError) as raised:
            validate_ack(429, {}, {"Retry-After": "900"}, now=0)
        self.assertTrue(raised.exception.throttle)
        self.assertEqual(raised.exception.delay, 900)
        self.assertFalse(raised.exception.ambiguous)

    def test_http_date_retry_after(self):
        self.assertEqual(retry_after("Thu, 01 Jan 1970 00:01:00 GMT", 10), 50)

    def test_200_negative_business_code_is_failure(self):
        with self.assertRaises(DeliveryError) as raised:
            validate_ack(200, {"ret": -2, "errmsg": "too frequent"})
        self.assertTrue(raised.exception.throttle)

    def test_minus_two_unknown_is_session_not_rate_limit(self):
        with self.assertRaises(DeliveryError) as raised:
            validate_ack(200, {"errcode": -2, "errmsg": "unknown error"})
        self.assertEqual(raised.exception.code, "session_expired")
        self.assertTrue(raised.exception.account_pause)
        self.assertFalse(raised.exception.throttle)

    def test_empty_malformed_and_boolean_ack_are_not_success(self):
        for body in ({}, [], {"ret": None}, {"ret": False}, {"ret": "0"}):
            with self.subTest(body=body), self.assertRaises(DeliveryError): validate_ack(200, body)

    def test_success_requires_explicit_zero(self):
        self.assertEqual(validate_ack(200, {"ret": 0}), {"ret": 0})
        self.assertEqual(validate_ack(200, {"ret": 0, "errcode": 0}), {"ret": 0, "errcode": 0})

    def test_5xx_and_timeout_are_ambiguous(self):
        with self.assertRaises(DeliveryError) as raised: validate_ack(503, {})
        self.assertTrue(raised.exception.ambiguous)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.clock = Clock()
        self.s = Store(self.root/"state.db", clock=self.clock)
    async def asyncTearDown(self): self.temp.cleanup()

    async def test_repeated_rate_limits_then_success_exact_physical_ids(self):
        mid = queue(self.s, parts=[Part("text", text="one"), Part("text", text="two"), Part("file", data=b"x", filename="x")])
        calls = []; accepted = []
        class Transport:
            async def send(inner, part):
                calls.append(part["id"])
                if len(calls) in (1, 3, 4):
                    raise DeliveryError("rate", throttle=True)
                accepted.append(part["id"])
        w = Worker(self.s, "account", Transport(), jitter=lambda: 0)
        for _ in range(6):
            self.assertTrue(await w.step())
            self.assertFalse(await w.step())
            self.clock.advance()
        self.assertEqual(self.s.status(mid)["state"], "accepted")
        self.assertEqual(len(accepted), 3)
        self.assertEqual(len(set(accepted)), 3)

    async def test_cancelled_attempt_recovers_without_disappearance(self):
        mid = queue(self.s)
        reached = asyncio.Event()
        class Transport:
            async def send(inner, part):
                reached.set(); await asyncio.Event().wait()
        task = asyncio.create_task(Worker(self.s, "account", Transport()).step())
        await reached.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(self.s.status(mid)["parts"][0]["state"], "sending")
        self.s.recover("account", "new")
        self.assertEqual(self.s.status(mid)["parts"][0]["ambiguous"], 1)

    async def test_cancelled_db_thread_is_drained_before_lock_release(self):
        import threading
        reached, done = threading.Event(), threading.Event()
        def operation():
            reached.set(); time.sleep(0.04); done.set()
        task = asyncio.create_task(run_io(operation))
        while not reached.is_set(): await asyncio.sleep(0.001)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(done.is_set())

    async def test_actual_local_http_429_then_200_and_latest_context(self):
        import aiohttp
        from aiohttp import web
        calls = []
        async def endpoint(request):
            calls.append(await request.json())
            if len(calls) == 1:
                return web.json_response({"ret": -2}, status=429, headers={"Retry-After": "40"})
            return web.json_response({"ret": 0, "errcode": 0})
        app = web.Application(); app.router.add_post("/ilink/bot/sendmessage", endpoint)
        runner = web.AppRunner(app); await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0); await site.start()
        port = site._server.sockets[0].getsockname()[1]
        wx = types.ModuleType("gateway.platforms.weixin")
        wx._json_dumps = canonical; wx._base_info = lambda: {}
        wx._headers = lambda token, body: {"Content-Type": "application/json", "Authorization": "Bearer "+token}
        wx.ITEM_TEXT=1; wx.MSG_TYPE_BOT=2; wx.MSG_STATE_FINISH=2; wx.EP_SEND_MESSAGE="ilink/bot/sendmessage"
        platforms = types.ModuleType("gateway.platforms"); platforms.weixin=wx
        context = ["context_before_retry"]
        try:
            async with aiohttp.ClientSession() as session:
                adapter = types.SimpleNamespace(_account_id="account", _owner_profile="default",
                    _token="TEST_ONLY_NOT_A_REAL_CREDENTIAL", _send_session=session,
                    _base_url=f"http://127.0.0.1:{port}",
                    _token_store=types.SimpleNamespace(get=lambda account, peer: context[0]))
                with mock.patch.dict(sys.modules, {"gateway.platforms": platforms, "gateway.platforms.weixin": wx}):
                    mid = queue(self.s)
                    w = Worker(self.s, "account", binding.ILinkTransport(adapter), jitter=lambda: 0)
                    await w.step()
                    self.clock.advance(39); self.assertFalse(await w.step())
                    context[0] = "new_context_after_retry"
                    self.clock.advance(1); await w.step()
            self.assertEqual(self.s.status(mid)["state"], "accepted")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0]["msg"]["client_id"], calls[1]["msg"]["client_id"])
            self.assertNotEqual(calls[0]["msg"]["context_token"], calls[1]["msg"]["context_token"])
            with self.s.connect() as c:
                dump = "\n".join(c.iterdump())
            self.assertNotIn("TEST_ONLY_NOT_A_REAL_CREDENTIAL", dump)
            self.assertNotIn("context_before_retry", dump)
            self.assertNotIn("new_context_after_retry", dump)
        finally:
            await runner.cleanup()


if __name__ == "__main__": unittest.main()
