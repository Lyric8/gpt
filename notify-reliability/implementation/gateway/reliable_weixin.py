"""Hermes/iLink binding. No bot token, context token or CDN key is persisted here.

Imported lazily by small, source-pinned Hermes hooks. Network retries belong
exclusively to reliable_outbox.Worker, not to the old adapter retry stack.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import math
import os
import secrets
import stat
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from gateway.reliable_outbox import (
    AccountLock, DeliveryError, Part, Store, Worker, canonical, digest,
    split_exact, validate_ack, run_io,
)

log = logging.getLogger(__name__)
_STORES: dict[str, Store] = {}


def home() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home())


def settings() -> dict:
    path = home() / "reliable-weixin.json"
    if not path.exists():
        raise RuntimeError("reliability_control_file_missing_no_raw_fallback")
    # A malformed or insecure control file must not re-enable the old sender.
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o022:
        raise RuntimeError("unsafe_reliable_weixin_config")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or not isinstance(cfg.get("enabled"), bool):
        raise ValueError("invalid_reliable_weixin_config")
    gap = cfg.get("gap_seconds", 20)
    if isinstance(gap, bool) or not isinstance(gap, (float, int)) or not math.isfinite(gap) or gap < 1:
        raise ValueError("invalid_gap_seconds")
    if not cfg["enabled"]:
        raise RuntimeError("disable_requires_stopped_source_rollback_no_raw_fallback")
    cfg.setdefault("gap_seconds", 20)
    return cfg


def enabled(adapter: Any = None) -> bool:
    if adapter is not None and str(getattr(getattr(adapter, "platform", None), "value", "")) != "weixin":
        return False
    return settings()["enabled"]


def store() -> Store:
    path = str(home() / "state.db")
    if path not in _STORES:
        _STORES[path] = Store(path)
    return _STORES[path]


def route(adapter: Any) -> tuple[str, str]:
    account = str(adapter._account_id)
    profile = str(getattr(adapter, "_owner_profile", None) or "default")
    if not account:
        raise ValueError("missing_transport_account")
    return account, profile


def snapshot(path: str, *, max_bytes: int = 32 * 1024 * 1024) -> bytes:
    # Open once, reject directories/devices/symlink endpoints. No temp filenames.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError("unsupported_attachment_size_or_type")
        with os.fdopen(fd, "rb", closefd=False) as f:
            data = f.read(max_bytes + 1)
        after = os.fstat(fd)
        if len(data) > max_bytes or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("attachment_changed_during_snapshot")
        return data
    finally:
        os.close(fd)


def text_parts(mid: str, text: str) -> list[Part]:
    pieces = split_exact(text)
    # The stable identifier is visible on FIRST transmission too. The payload
    # never changes on uncertain replay, so a provider can deduplicate if it
    # happens to implement client_id idempotency (not assumed by this module).
    return [Part("text", text=f"【{mid[:12]} {n+1}/{len(pieces)}】\n" + p)
            for n, p in enumerate(pieces)]


async def plan(adapter: Any, row: dict) -> list[Part]:
    raw = json.loads(row["raw"])
    body = str(raw.get("body") or "")
    files: list[tuple[str, bool]] = []
    urls: list[str] = []
    force = bool(raw.get("force_file"))
    if raw["type"] == "final":
        force = force or "[[as_document]]" in body
        media, body = adapter.extract_media(body)
        # Preserve the existing platform's access-control/path filtering.
        allowed_media = adapter.filter_media_delivery_paths(media, session_key=row.get("session_key"))
        if allowed_media != media:
            raise ValueError("requested_attachment_filtered_requires_review")
        media = allowed_media
        images, body = adapter.extract_images(body)
        local, body = adapter.extract_local_files(body)
        local = adapter.filter_local_delivery_paths(local, session_key=row.get("session_key"))
        files.extend((str(p), bool(v)) for p, v in media)
        files.extend((str(p), False) for p in local)
        urls.extend(str(url) for url, _ in images)
        body = body.replace("[[as_document]]", "").replace("[[audio_as_voice]]", "")
    elif raw["type"] == "text":
        media, body = adapter.extract_media(body)
        allowed_media = adapter.filter_media_delivery_paths(media)
        if allowed_media != media:
            raise ValueError("requested_attachment_filtered_requires_review")
        files.extend((str(p), bool(v)) for p, v in allowed_media)
    files.extend((str(p[0]), bool(p[1])) for p in raw.get("files", []))
    urls.extend(str(u) for u in raw.get("urls", []))
    # Do not silently remove unsupported directives or missing explicit assets.
    # The raw reply always remains stored for operator inspection/re-planning.
    result = text_parts(row["id"], adapter.format_message(body)) if body else []
    total = 0
    seen: set[str] = set()
    for path, voice in files:
        if path in seen:
            continue
        seen.add(path)
        data = await run_io(snapshot, path)
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise ValueError("attachment_bundle_too_large")
        result.append(Part("file", data=data, filename=Path(path).name, force_file=force or voice))
    for url in urls:
        # Downloading remote images is intentionally disabled in this first
        # production contract: arbitrary URLs/redirects can introduce SSRF and
        # expiring objects. Preserve a clickable link instead of deleting it.
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("unsupported_remote_attachment")
        result.extend(text_parts(row["id"], "图片链接（未作为附件投递）：" + url))
    if not result:
        raise ValueError("no_deliverable_parts")
    return result


async def _plan_once(adapter: Any, row: dict) -> None:
    try:
        parts = await plan(adapter, row)
    except asyncio.CancelledError:
        raise
    except Exception:
        await run_io(store().block_plan, row["id"], "attachment_or_render_plan_failed")
        log.error("wx_outbox_plan_blocked id=%s", row["id"])
    else:
        await run_io(store().finish_plan, row["id"], parts)


def _row(mid: str) -> dict:
    with store().connect() as c:
        row = c.execute("SELECT * FROM wx_outbox_messages WHERE id=?", (mid,)).fetchone()
        if not row:
            raise KeyError(mid)
        return dict(row)


async def _clear_resume(runner: Any, session_key: str) -> None:
    if runner is None or not hasattr(runner, "async_session_store"):
        raise RuntimeError("missing_resume_barrier")
    await runner.async_session_store.clear_resume_pending(session_key)


async def capture_final(adapter: Any, event: Any, session_key: str, response: str) -> str:
    delivery = adapter._final_delivery_adapter(event.source)
    account, profile = route(delivery)
    inbound_id = str(getattr(event, "message_id", None) or "")
    # Missing transport identity is not permission to discard a generated
    # reply. Preserve it in a blocked envelope for an explicit repair decision.
    key = (canonical(["final", session_key, inbound_id]) if inbound_id
           else "unidentified-final:" + uuid.uuid4().hex)
    mid = await run_io(store().reserve, account=account, profile=profile,
                                 chat=str(event.source.chat_id), key=key,
                                 raw={"type": "final", "body": response}, session=session_key,
                                 ready=False, category="reply")
    row = await run_io(_row, mid)
    if not inbound_id:
        await run_io(store().block_plan, mid, "missing_inbound_message_id")
    elif row["state"] == "preparing":
        await _plan_once(delivery, row)
    # Keep the session's current owner until resume state is durably cleared.
    # Cancellation leaves ready=0; startup barrier must finish this BEFORE
    # upstream is allowed to schedule interrupted agent turns.
    while not (await run_io(store().status, mid))["ready"]:
        try:
            await _clear_resume(getattr(adapter, "gateway_runner", None), session_key)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("wx_outbox_resume_barrier_wait id=%s", mid)
            await asyncio.sleep(5)
        else:
            await run_io(store().activate, mid)
    log.info("wx_outbox_admitted id=%s provider_accepted=false", mid)
    return mid


async def restore_before_resume(runner: Any) -> None:
    if not enabled():
        return
    # A failed clear propagates: boot must not rerun an already-generated turn.
    for row in await run_io(store().held):
        if row["session_key"]:
            await _clear_resume(runner, row["session_key"])
        await run_io(store().activate, row["id"])


async def submit(adapter: Any, chat: str, *, body: str = "", files: list | None = None,
                 urls: list | None = None, key: str | None = None, force_file: bool = False) -> Any:
    from gateway.platforms.base import SendResult
    account, profile = route(adapter)
    key = key or "call:" + uuid.uuid4().hex
    mid = await run_io(store().reserve, account=account, profile=profile, chat=str(chat),
                                 key=key, raw={"type": "text", "body": body, "files": files or [],
                                              "urls": urls or [], "force_file": force_file},
                                 session=None, ready=True, category="notification")
    row = await run_io(_row, mid)
    if row["state"] == "preparing":
        await _plan_once(adapter, row)
    status = await run_io(store().status, mid)
    if status["state"] == "accepted":
        return SendResult(success=True, message_id=mid)
    # Do NOT masquerade local admission as successful platform delivery.
    return SendResult(success=False, message_id=mid, error="durable_queued:" + mid)


async def submit_method(adapter: Any, method: str, values: dict) -> Any:
    metadata = values.get("metadata") or {}
    key = metadata.get("delivery_key")
    chat = values["chat_id"]
    if method in {"send", "_send_with_retry"}:
        return await submit(adapter, chat, body=values["content"], key=key)
    caption = values.get("caption") or ""
    if method == "send_image":
        url = values["image_url"]
        if url.startswith(("http://", "https://")):
            return await submit(adapter, chat, body=caption, urls=[url], key=key)
        path = url.removeprefix("file://")
    else:
        path = next(values[k] for k in ("file_path", "image_path", "video_path", "audio_path") if k in values)
    return await submit(adapter, chat, body=caption, files=[(str(path), method == "send_voice")],
                        key=key, force_file=method in {"send_document", "send_voice"})


async def enqueue_direct(*, extra: dict, token: str | None, chat_id: str, message: str,
                         media_files: list | None = None) -> dict:
    from gateway.platforms.weixin import WeixinAdapter, PlatformConfig, _wx_secret
    account = str(extra.get("account_id") or _wx_secret("WEIXIN_ACCOUNT_ID", ""))
    adapter = WeixinAdapter(PlatformConfig(enabled=True, token=token, extra={**extra, "account_id": account}))
    adapter._owner_profile = str(extra.get("delivery_profile") or "default")
    result = await submit(adapter, chat_id, body=message, files=media_files,
                          key=extra.get("delivery_key"))
    return {"success": result.success, "queued": not result.success,
            "message_id": result.message_id, "error": result.error,
            "delivery_state": "accepted" if result.success else "durable_pending"}


class ILinkTransport:
    def __init__(self, adapter: Any):
        self.adapter = adapter

    async def post(self, endpoint: str, payload: dict, *, timeout: float = 15,
                   delivery: bool = True) -> dict:
        from gateway.platforms import weixin as wx
        a = self.adapter
        if not a._send_session or a._send_session.closed or not a._token:
            raise DeliveryError("adapter_disconnected", delay=30)
        body = wx._json_dumps({**payload, "base_info": wx._base_info()})
        try:
            async with asyncio.timeout(timeout):
                async with a._send_session.post(a._base_url.rstrip("/")+"/"+endpoint,
                                                data=body, headers=wx._headers(a._token, body),
                                                allow_redirects=False) as response:
                    raw = await response.content.read(1024 * 1024 + 1)
                    try:
                        result = json.loads(raw) if len(raw) <= 1024 * 1024 else None
                    except (ValueError, UnicodeError):
                        result = None
                    # Upload preparation can prove success by its mandatory
                    # URL/ticket fields. That is not a chat delivery receipt.
                    if (not delivery and 200 <= response.status < 300 and isinstance(result, dict)
                            and not any(k in result for k in ("ret", "errcode"))
                            and (result.get("upload_full_url") or result.get("upload_param"))):
                        return result
                    return validate_ack(response.status, result, response.headers)
        except DeliveryError as exc:
            # Upload preparation failures cannot have delivered a chat bubble.
            if not delivery:
                exc.ambiguous = False
            raise
        except (TimeoutError, OSError):
            raise DeliveryError("network_outcome_unknown" if delivery else "upload_prepare_failed",
                                ambiguous=delivery, delay=30) from None

    async def _media_item(self, part: dict) -> dict:
        from gateway.platforms import weixin as wx
        a = self.adapter
        data = part["data"]
        if not isinstance(data, bytes):
            raise DeliveryError("attachment_snapshot_missing", retry=False)
        aes_key, filekey = secrets.token_bytes(16), secrets.token_hex(16)
        ciphertext = await run_io(wx._aes128_ecb_encrypt, data, aes_key)
        media_type, builder = a._outbound_media_builder(part["filename"], force_file_attachment=bool(part["force_file"]))
        if part["force_file"]:
            media_type = wx.MEDIA_FILE
            builder = lambda **kw: {"type": wx.ITEM_FILE, "file_item": {
                "media": {"encrypt_query_param": kw["encrypt_query_param"], "aes_key": kw["aes_key_for_api"], "encrypt_type": 1},
                "file_name": kw["filename"], "len": str(kw["plaintext_size"])}}
        md5 = hashlib.md5(data).hexdigest()
        reply = await self.post(wx.EP_GET_UPLOAD_URL, {"filekey": filekey, "media_type": media_type,
            "to_user_id": part["chat"], "rawsize": len(data), "rawfilemd5": md5,
            "filesize": len(ciphertext), "no_need_thumb": True, "aeskey": aes_key.hex()}, delivery=False)
        url = reply.get("upload_full_url") or wx._cdn_upload_url(a._cdn_base_url, str(reply.get("upload_param") or ""), filekey)
        # Never send bearer credentials to a CDN; no redirects in this upload.
        wx._assert_weixin_cdn_url(url)
        try:
            async with asyncio.timeout(120):
                async with a._send_session.post(url, data=ciphertext, allow_redirects=False,
                        headers={"Content-Type": "application/octet-stream"}) as response:
                    await response.content.read(1024 * 1024)
                    param = response.headers.get("x-encrypted-param")
                    if response.status != 200 or not param:
                        if response.status == 429:
                            validate_ack(429, None, response.headers)
                        raise DeliveryError("cdn_upload_failed", delay=30)
        except (TimeoutError, OSError):
            raise DeliveryError("cdn_upload_failed", delay=30) from None
        return builder(encrypt_query_param=param,
                       aes_key_for_api=base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii"),
                       ciphertext_size=len(ciphertext), plaintext_size=len(data),
                       filename=part["filename"], rawfilemd5=md5)

    async def send(self, part: dict) -> None:
        from gateway.platforms import weixin as wx
        a = self.adapter
        if part["account"] != a._account_id or part["profile"] != route(a)[1]:
            raise DeliveryError("transport_route_mismatch", retry=False)
        item = ({"type": wx.ITEM_TEXT, "text_item": {"text": part["text"]}}
                if part["kind"] == "text" else await self._media_item(part))
        # Read after slow media upload, not when enqueuing the reply.
        context = a._token_store.get(a._account_id, part["chat"])
        if not context:
            raise DeliveryError("waiting_for_peer_context", delay=60)
        msg = {"from_user_id": "", "to_user_id": part["chat"],
               "client_id": "hermes-wx-"+part["id"][:32],
               "message_type": wx.MSG_TYPE_BOT, "message_state": wx.MSG_STATE_FINISH,
               "item_list": [item], "context_token": context}
        await self.post(wx.EP_SEND_MESSAGE, {"msg": msg})


class Runtime:
    def __init__(self, adapter: Any):
        self.adapter = adapter
        self.account, self.profile = route(adapter)
        self.owner = uuid.uuid4().hex
        self.lock = AccountLock(home()/"reliable-weixin-locks", self.account)
        self.tasks: list[asyncio.Task] = []
        self.worker = Worker(store(), self.account, ILinkTransport(adapter), gap=settings()["gap_seconds"])

    async def run(self) -> None:
        await run_io(store().recover, self.account, self.owner)
        while True:
            # Plan at most one envelope per cycle; network I/O never holds a DB transaction.
            row = await run_io(store().unplanned, self.account)
            if row:
                await _plan_once(self.adapter, row)
            await self.worker.step()
            await asyncio.sleep(0.5)

    async def monitor(self) -> None:
        next_cleanup = time.monotonic() + 3600
        while True:
            await run_io(store().heartbeat, self.account, self.owner)
            await run_io(store().notice, self.account)
            if time.monotonic() >= next_cleanup:
                await run_io(store().scrub_accepted_payloads)
                next_cleanup = time.monotonic() + 3600
            await asyncio.sleep(5)

    def done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            # Stop the heartbeat too: an independent watchdog must see failure.
            log.critical("wx_outbox_worker_failed exception_type=%s", type(exc).__name__)
            for other in self.tasks:
                if other is not task:
                    other.cancel()
            # Keep kernel ownership until orderly disconnect/process exit.


async def start(adapter: Any) -> None:
    if not enabled(adapter) or getattr(adapter, "_reliable_runtime", None):
        return
    s = store()
    account, profile = route(adapter)
    with s.transaction() as c:
        c.execute("INSERT OR IGNORE INTO wx_outbox_accounts(account,profile) VALUES (?,?)", (account, profile))
        if c.execute("SELECT profile FROM wx_outbox_accounts WHERE account=?", (account,)).fetchone()[0] != profile:
            raise RuntimeError("account_profile_conflict")
    runtime = Runtime(adapter)  # lock failure must prevent double senders
    adapter._reliable_runtime = runtime
    runtime.tasks = [asyncio.create_task(runtime.run(), name="wx-outbox-worker"),
                     asyncio.create_task(runtime.monitor(), name="wx-outbox-heartbeat")]
    for task in runtime.tasks:
        task.add_done_callback(runtime.done)


async def stop(adapter: Any) -> None:
    runtime = getattr(adapter, "_reliable_runtime", None)
    if not runtime:
        return
    for task in runtime.tasks:
        task.cancel()
    await asyncio.gather(*runtime.tasks, return_exceptions=True)
    runtime.lock.close()
    adapter._reliable_runtime = None
