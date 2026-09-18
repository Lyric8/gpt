"""Same-origin JSON API, HttpOnly anonymous identities, no public room enumeration."""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from urllib.parse import urlsplit
import anyio
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from .domain import Problem, require
from .store import Store

LOG = logging.getLogger('campfire.rooms')
MAX_BODY = 16384


class RateLimit:
    """Bounded process-local abuse protection; production runs exactly one API worker."""
    def __init__(self, clock=time.monotonic):
        self.clock, self.lock, self.buckets = clock, threading.Lock(), OrderedDict()
        self.salt = secrets.token_bytes(32)

    def check(self, kind, subject, limit, period):
        key = kind + ':' + hashlib.sha256(self.salt + subject.encode()).hexdigest()
        now = self.clock()
        with self.lock:
            bucket = self.buckets.get(key)
            if bucket is None:
                # Evict inactive buckets only; never evict an active rate limit to admit an attacker.
                if len(self.buckets) >= 20000:
                    for old_key, (last, old_period, _) in list(self.buckets.items()):
                        if now - last >= old_period:
                            del self.buckets[old_key]
                    require(len(self.buckets) < 20000, '服务繁忙，请稍后重试。', 'RATE_LIMIT', 429)
                times = deque()
            else:
                times = bucket[2]
            while times and now - times[0] >= period:
                times.popleft()
            require(len(times) < limit, '操作过于频繁，请稍后再试。', 'RATE_LIMIT', 429)
            times.append(now)
            self.buckets[key] = (now, period, times)


async def body(request: Request) -> dict:
    require(request.headers.get('content-type', '').split(';')[0] == 'application/json', '仅接受JSON请求。', 'CONTENT_TYPE', 415)
    raw = bytearray()
    try:
        with anyio.fail_after(10):
            async for chunk in request.stream():
                raw.extend(chunk)
                require(len(raw) <= MAX_BODY, '请求内容过大。', 'BODY_LIMIT', 413)
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non-finite')))
        require(isinstance(value, dict), '请求必须是对象。')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise Problem(400, 'INVALID_JSON', 'JSON格式不正确。') from None
    except TimeoutError:
        raise Problem(408, 'REQUEST_TIMEOUT', '请求超时，请重试。') from None


def create_app(store: Store, origin: str, secure=True, require_archiver=True) -> Starlette:
    parsed = urlsplit(origin)
    if parsed.path not in ('', '/') or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError('ROOMS_ORIGIN must be an exact origin')
    if secure and parsed.scheme != 'https':
        raise ValueError('Production requires HTTPS')
    if not secure and parsed.hostname not in ('127.0.0.1', 'localhost', 'testserver'):
        raise ValueError('Insecure cookies are restricted to loopback tests')
    origin = origin.rstrip('/')
    cookie = '__Host-campfire-device' if secure else 'campfire-device-dev'
    limiter = RateLimit()

    def token(request):
        return request.cookies.get(cookie, '')

    async def health(request):
        ready = await run_in_threadpool(store.archiver_ready)
        return JSONResponse({'protocol': 1, 'enabled': True, 'archiveReady': ready})

    async def session(request):
        await body(request)
        limiter.check('session', request.client.host, 60, 3600)
        value = await run_in_threadpool(store.session, token(request))
        response = JSONResponse({'ok': True})
        response.set_cookie(cookie, value, max_age=30 * 86400, secure=secure, httponly=True, samesite='strict', path='/')
        return response

    async def create(request):
        value = await body(request)
        limiter.check('create-ip', request.client.host, 12, 3600)
        limiter.check('create-global', 'all', 300, 3600)
        if require_archiver:
            require(await run_in_threadpool(store.archiver_ready), '归档服务尚未就绪，暂不能创建新房间。已有房间不受影响。', 'ARCHIVE_NOT_READY', 503)
        result = await run_in_threadpool(store.create, value, token(request))
        return JSONResponse(result, status_code=201)

    async def join(request):
        value = await body(request)
        limiter.check('join-ip', request.client.host, 30, 60)
        limiter.check('join-global', 'all', 240, 60)
        return JSONResponse(await run_in_threadpool(store.join, value, token(request)))

    async def read(request):
        limiter.check('read', token(request) or request.client.host, 150, 60)
        after = request.query_params.get('after', '-1')
        require(len(after) <= 10 and after.lstrip('-').isdigit(), '版本参数无效。')
        return JSONResponse(await run_in_threadpool(store.snapshot, request.path_params['room_id'], token(request), int(after)))

    async def catalog(request):
        limiter.check('catalog', token(request) or request.client.host, 20, 60)
        return JSONResponse(await run_in_threadpool(store.catalog, request.path_params['room_id'], token(request)))

    async def operate(request):
        value = await body(request)
        limiter.check('operation', token(request) or request.client.host, 120, 60)
        return JSONResponse(await run_in_threadpool(store.operate, request.path_params['room_id'], token(request), value))

    async def missing(request, exception):
        return JSONResponse({'error': {'code': 'NOT_FOUND', 'message': '接口不存在。'}}, status_code=404)

    app = Starlette(routes=[
        Route('/api/rooms/health', health, methods=['GET']),
        Route('/api/rooms/session', session, methods=['POST']),
        Route('/api/rooms', create, methods=['POST']),
        Route('/api/rooms/join', join, methods=['POST']),
        Route('/api/rooms/{room_id}/catalog', catalog, methods=['GET']),
        Route('/api/rooms/{room_id}/ops', operate, methods=['POST']),
        Route('/api/rooms/{room_id}', read, methods=['GET']),
    ], exception_handlers={404: missing, 405: missing})

    async def guard(request, call_next):
        try:
            require(request.headers.get('host') == parsed.netloc, '请求来源不正确。', 'ORIGIN', 403)
            if request.url.path.startswith('/api/rooms') and request.url.path != '/api/rooms/health':
                require(request.headers.get('x-room-client') == '1', '请从火边页面操作。', 'ORIGIN', 403)
                require(request.headers.get('sec-fetch-site', 'same-origin') in ('same-origin', 'none'), '不接受跨站请求。', 'ORIGIN', 403)
            if request.method not in ('GET', 'HEAD'):
                require(request.headers.get('origin') == origin, '不接受跨站修改。', 'ORIGIN', 403)
                length = request.headers.get('content-length', '0')
                require(length.isdigit() and int(length) <= MAX_BODY, '请求内容过大。', 'BODY_LIMIT', 413)
            response = await call_next(request)
        except Problem as exc:
            response = JSONResponse({'error': {'code': exc.code, 'message': exc.message}}, status_code=exc.status)
        except Exception:
            LOG.exception('rooms_request_failed')  # Never log request bodies, cookies or PINs.
            response = JSONResponse({'error': {'code': 'SERVER_ERROR', 'message': '暂时无法保存，稍后可重试。'}}, status_code=503)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                                 'Referrer-Policy': 'no-referrer', 'X-Robots-Tag': 'noindex, nofollow'})
        if response.status_code == 429:
            response.headers['Retry-After'] = '60'
        return response
    app.add_middleware(BaseHTTPMiddleware, dispatch=guard)
    return app


def production_app():
    """Uvicorn --factory target. Credentials for GitHub must NOT be in this service."""
    from tools.catalog import load_catalog
    root = Path(__file__).resolve().parents[2]
    catalog = {'database': load_catalog(root), 'equipment': json.loads((root / 'data/equipment.json').read_text())}
    store = Store(os.environ['ROOMS_DATABASE'], catalog)
    return create_app(store, os.environ['ROOMS_ORIGIN'])
