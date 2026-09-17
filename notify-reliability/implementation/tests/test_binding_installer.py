import asyncio
import dataclasses
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gateway.reliable_outbox import Store
from gateway import reliable_weixin as binding
spec = importlib.util.spec_from_file_location("wx_install", ROOT/"install.py")
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


class Adapter:
    _account_id = "account"
    _owner_profile = "default"
    platform = types.SimpleNamespace(value="weixin")
    def __init__(self):
        self.gateway_runner = types.SimpleNamespace(async_session_store=types.SimpleNamespace(clear_resume_pending=mock.AsyncMock()))
    def _final_delivery_adapter(self, source): return self
    def extract_media(self, body):
        files = []; text = []
        for line in body.splitlines(keepends=True):
            if line.startswith("MEDIA:"):
                files.append((line[6:].strip(), False))
            else: text.append(line)
        return files, "".join(text)
    def filter_media_delivery_paths(self, items, **kwargs): return items
    def filter_local_delivery_paths(self, items, **kwargs): return items
    def extract_images(self, text): return [], text
    def extract_local_files(self, text): return [], text
    def format_message(self, text): return text


class BindingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.s=Store(self.root/"state.db")
        self.adapter=Adapter()
        self.event=types.SimpleNamespace(message_id="incoming-1", source=types.SimpleNamespace(chat_id="peer"))
        self.patch=mock.patch.object(binding, "store", return_value=self.s); self.patch.start()
        self.homepatch=mock.patch.object(binding, "home", return_value=self.root); self.homepatch.start()
        (self.root/"reliable-weixin.json").write_text('{"enabled":true,"gap_seconds":20}')
    async def asyncTearDown(self):
        self.homepatch.stop(); self.patch.stop(); self.temp.cleanup()

    async def test_capture_raw_before_resume_and_media_snapshot(self):
        path=self.root/"r.pdf"; path.write_bytes(b"REPORT")
        async def clear(session):
            held=self.s.held()
            self.assertEqual(len(held),1)
            self.assertEqual(self.s.status(held[0]["id"])["state"], "queued")
            self.assertIsNone(self.s.claim("account"))
        self.adapter.gateway_runner.async_session_store.clear_resume_pending=clear
        raw="结论\nMEDIA:"+str(path)
        mid=await binding.capture_final(self.adapter,self.event,"session",raw)
        path.unlink()
        self.assertEqual(self.s.status(mid)["ready"],1)
        with self.s.connect() as c:
            stored=c.execute("SELECT data FROM wx_outbox_parts WHERE kind='file'").fetchone()[0]
            self.assertEqual(stored,b"REPORT")
            self.assertEqual(json.loads(c.execute("SELECT raw FROM wx_outbox_messages").fetchone()[0])["body"],raw)

    async def test_missing_attachment_is_not_parent_success(self):
        mid=await binding.capture_final(self.adapter,self.event,"session","text\nMEDIA:"+str(self.root/"missing.pdf"))
        self.assertEqual(self.s.status(mid)["state"],"blocked")
        self.assertIsNone(self.s.claim("account"))

    async def test_cancel_resume_barrier_then_boot_recovery(self):
        reached=asyncio.Event()
        async def clear(session): reached.set(); await asyncio.Event().wait()
        self.adapter.gateway_runner.async_session_store.clear_resume_pending=clear
        task=asyncio.create_task(binding.capture_final(self.adapter,self.event,"session","report"))
        await reached.wait(); task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        mid=self.s.held()[0]["id"]
        self.assertIsNone(self.s.claim("account"))
        runner=types.SimpleNamespace(async_session_store=types.SimpleNamespace(clear_resume_pending=mock.AsyncMock()))
        await binding.restore_before_resume(runner)
        runner.async_session_store.clear_resume_pending.assert_awaited_once_with("session")
        self.assertEqual(self.s.status(mid)["ready"],1)

    async def test_repeated_final_event_has_one_envelope(self):
        one=await binding.capture_final(self.adapter,self.event,"session","report")
        two=await binding.capture_final(self.adapter,self.event,"session","report")
        self.assertEqual(one,two)
        with self.s.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM wx_outbox_messages").fetchone()[0],1)

    async def test_resume_clear_failure_cannot_fall_through_to_agent_restart(self):
        mid=self.s.reserve(account="account", profile="default", chat="peer", key="held",
                           raw={"type":"text","body":"report"},session="session",ready=False,category="reply")
        runner=types.SimpleNamespace(async_session_store=types.SimpleNamespace(clear_resume_pending=mock.AsyncMock(side_effect=OSError())))
        with self.assertRaises(OSError): await binding.restore_before_resume(runner)
        self.assertEqual(self.s.status(mid)["ready"],0)

    async def test_config_disappearance_or_false_cannot_reenable_raw_sends(self):
        path=self.root/"reliable-weixin.json"
        path.unlink()
        with self.assertRaises(RuntimeError): binding.enabled(self.adapter)
        path.write_text('{"enabled":false}')
        with self.assertRaises(RuntimeError): binding.enabled(self.adapter)

    async def test_missing_inbound_id_preserves_generated_reply(self):
        self.event.message_id = None
        mid = await binding.capture_final(self.adapter, self.event, "session", "valuable report")
        self.assertEqual(self.s.status(mid)["state"], "blocked")
        self.assertEqual(self.s.status(mid)["error"], "missing_inbound_message_id")
        with self.s.connect() as c:
            self.assertIn("valuable report", c.execute("SELECT raw FROM wx_outbox_messages").fetchone()[0])

    async def test_other_platform_is_not_intercepted(self):
        other=types.SimpleNamespace(platform=types.SimpleNamespace(value="telegram"))
        self.assertFalse(binding.enabled(other))

    async def test_filtered_explicit_attachment_cannot_be_reported_accepted(self):
        path=self.root/"r.pdf"; path.write_bytes(b"x")
        self.adapter.filter_media_delivery_paths=lambda items, **kwargs: []
        mid=await binding.capture_final(self.adapter,self.event,"session","正文\nMEDIA:"+str(path))
        self.assertEqual(self.s.status(mid)["state"],"blocked")


class InstallerTests(unittest.TestCase):
    def fixture(self):
        base='''class Base:
    async def _send_with_retry(self, chat_id, content, reply_to=None, metadata=None):
        """ordinary retry"""
        return await self.send(chat_id, content)
    async def _process_message_background(self, event, session_key):
        if True:
            response = "hello"
            if not response:
                logger.debug("[%s] Handler returned empty/None response for %s", self.name, event.source.chat_id)
'''
        wx='class Adapter:\n'
        for name in ("send","send_document","send_voice","send_video","send_image_file","send_image",
                     "_send_file","_send_text_chunk","_send_text_chunk_locked","disconnect"):
            wx+=f'    async def {name}(self, **kwargs):\n        """doc"""\n        return None\n'
        wx+='''    async def connect(self):
        _LIVE_ADAPTERS[self._token] = self
        return True
async def send_weixin_direct(*, extra, token, chat_id, message, media_files=None):
    return {}
'''
        run='''class Runner:
    async def _claim_pending_obligations(self):
        """startup"""
        rows = sweep_recoverable()
        await self._clear_resume_pending_for_claimed_obligations(rows)
        return rows
'''
        ledger='''SQL = """SELECT obligation_id FROM delivery_obligations
                         ORDER BY CASE state
                         WHEN 'delivered' THEN 0 ELSE 1 END"""
STARTUP = "WHERE state IN ('pending', 'attempting', 'failed')"
RUNTIME = "WHERE state='failed' AND platform=?"
'''
        return {"gateway/platforms/base.py":base,"gateway/platforms/weixin.py":wx,
                "gateway/run.py":run,"gateway/delivery_ledger.py":ledger}

    def test_source_hooks_compile_and_do_not_remove_original_logic(self):
        sources=self.fixture()
        changed=installer.edit_sources(sources)
        for path,source in changed.items(): compile(source,path,"exec")
        self.assertIn('response = None  # processing complete',changed["gateway/platforms/base.py"])
        self.assertIn("return await self.send",changed["gateway/platforms/base.py"])
        self.assertIn("restore_before_resume(self)",changed["gateway/run.py"])
        self.assertIn("WHERE state IN ('delivered', 'abandoned')",changed["gateway/delivery_ledger.py"])

    def test_changed_anchor_is_fail_closed(self):
        sources=self.fixture()
        sources["gateway/platforms/base.py"]=sources["gateway/platforms/base.py"].replace("Handler returned empty/None", "changed")
        with self.assertRaises(ValueError): installer.edit_sources(sources)

    def test_duplicate_function_is_fail_closed(self):
        with self.assertRaises(ValueError): installer.enter("def f(): pass\ndef f(): pass\n", "f", "pass")

    def test_blob_pinning_stops_unknown_production_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"hermes"; root.mkdir()
            for path,source in self.fixture().items():
                p=root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(source)
            before=(root/"gateway/platforms/base.py").read_bytes()
            with self.assertRaisesRegex(ValueError,"pinned_blob_mismatch"):
                installer.make_stage(root,Path(d)/"stage")
            self.assertEqual((root/"gateway/platforms/base.py").read_bytes(),before)

    def test_live_service_refuses_apply(self):
        result=types.SimpleNamespace(stdout="LoadState=loaded\nActiveState=active\nMainPID=123\n")
        with mock.patch.object(installer.subprocess,"run",return_value=result), self.assertRaises(RuntimeError):
            installer.require_stopped(["hermes-gateway.service"],user=False)

    def test_pending_queue_refuses_destructive_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);s=Store(root/"state.db")
            s.reserve(account="a",profile="default",chat="p",key="k",raw={"body":"owed"},session=None,ready=True,category="reply")
            with mock.patch.object(installer,"require_stopped"), self.assertRaisesRegex(RuntimeError,"rollback_refused_pending"):
                installer.rollback(root/"nonexistent-backup",root,["unit"],user=False)


if __name__ == "__main__": unittest.main()
