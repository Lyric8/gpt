"""SQLite authority: short serializable mutations, immutable catalog snapshots, hard TTL.

The API and archive worker use separate processes/connections. No network operation may
run while holding a transaction. WAL must be on a local filesystem, not a network share.
"""
from __future__ import annotations
import contextlib
import json
import math
import secrets
import sqlite3
import time
from pathlib import Path
from .domain import (WEEK, INSTANCE, OP_ID, Problem, aggregate, archive_document, archive_path,
                     canonical, check_pin, digest, empty_choices, encode_pin, identity, require)


class Store:
    def __init__(self, path: str | Path, catalog: dict | None = None, clock=time.time):
        self.path, self.clock = str(path), clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(Path(__file__).with_name('schema.sql').read_text())
            if db.execute('SELECT version FROM schema_info').fetchone()[0] != 1:
                raise RuntimeError('Unsupported room database version')
        self.catalog_hash = None
        if catalog is not None:
            payload = canonical(catalog)
            self.catalog_hash = digest(payload)
            with self.transaction(True) as db:
                db.execute('INSERT OR IGNORE INTO catalogs VALUES(?,?)', (self.catalog_hash, payload))

    @contextlib.contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def transaction(self, write=False):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def session(self, token: str) -> str:
        with self.transaction(True) as db:
            now = self.clock()
            existing = db.execute('SELECT hash FROM devices WHERE hash=? AND expires>?', (digest(token), now)).fetchone() if token else None
            if existing:
                db.execute('UPDATE devices SET expires=? WHERE hash=?', (now + 30 * WEEK / 7, existing['hash']))
                return token
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO devices VALUES(?,?)', (digest(token), now + 30 * WEEK / 7))
            return token

    def _device(self, db, token):
        require(isinstance(token, str) and len(token) == 43, '请重新进入房间。', 'SESSION_REQUIRED', 401)
        device = digest(token)
        require(db.execute('SELECT 1 FROM devices WHERE hash=? AND expires>?', (device, self.clock())).fetchone() is not None,
                '浏览器身份已过期，请重新进入。', 'SESSION_REQUIRED', 401)
        return device

    def _active(self, db, room_id):
        require(isinstance(room_id, str) and INSTANCE.fullmatch(room_id) is not None,
                '房间不存在或已到期。', 'ROOM_UNAVAILABLE', 404)
        row = db.execute("SELECT * FROM rooms WHERE id=? AND status='active' AND expires>?", (room_id, self.clock())).fetchone()
        require(row is not None, '房间不存在或已到期。', 'ROOM_UNAVAILABLE', 404)
        return dict(row)

    def _auth(self, db, room_id, token):
        device = self._device(db, token)
        room = self._active(db, room_id)
        member = db.execute('SELECT * FROM members WHERE room_id=? AND device_hash=?', (room_id, device)).fetchone()
        require(member is not None, '请用房号和口令加入。', 'MEMBERSHIP_REQUIRED', 403)
        return room, dict(member)

    @staticmethod
    def _catalog(db, key):
        return json.loads(db.execute('SELECT payload FROM catalogs WHERE hash=?', (key,)).fetchone()[0])

    @staticmethod
    def _members(db, room_id):
        rows = db.execute('SELECT id,nickname,choices FROM members WHERE room_id=? ORDER BY id', (room_id,)).fetchall()
        return [{**dict(row), 'choices': json.loads(row['choices'])} for row in rows]

    def _snapshot(self, db, room, member_id):
        members = self._members(db, room['id'])
        settings = json.loads(room['settings'])
        return {'protocol': 1, 'id': room['id'], 'number': room['number'],
                'createdAt': room['created'], 'expiresAt': room['expires'], 'serverTime': self.clock(),
                'revision': room['revision'], 'locked': bool(room['pin_hash']), 'host': room['host'], 'memberId': member_id,
                'catalogHash': room['catalog_hash'], 'members': members, 'settings': settings,
                **aggregate(members, settings)}

    def create(self, data: dict, token: str) -> dict:
        number, nickname, pin = identity(data)
        require(self.catalog_hash is not None, '房间服务尚未配置菜谱。', 'NOT_READY', 503)
        salt, hashed_pin = encode_pin(pin)
        request_hash = digest(canonical({k: v for k, v in data.items() if k != 'passcode'}))
        with self.transaction() as prior_db:
            prior = prior_db.execute('SELECT pin_salt,pin_hash FROM rooms WHERE number=?', (number,)).fetchone()
        same_pin = prior is not None and bool(pin) == bool(prior['pin_hash']) and check_pin(pin, prior['pin_salt'], prior['pin_hash'])
        with self.transaction(True) as db:
            device, now = self._device(db, token), self.clock()
            old = db.execute('SELECT * FROM rooms WHERE number=?', (number,)).fetchone()
            if old:
                member = db.execute('SELECT * FROM members WHERE room_id=? AND device_hash=?', (old['id'], device)).fetchone()
                if member and member['id'] == old['host'] and old['create_hash'] == request_hash and same_pin:
                    room = self._active(db, old['id'])
                    return self._snapshot(db, room, member['id'])
                raise Problem(409, 'NUMBER_TAKEN', '这个房号已使用或封存，请换一个。')
            active_count = db.execute("SELECT count(*) FROM rooms WHERE status='active' AND expires>?", (now,)).fetchone()[0]
            require(active_count < 500, '房间已满，请稍后再建。', 'CAPACITY', 503)
            room_id, member_id = secrets.token_hex(16), secrets.token_hex(16)
            settings = canonical({'people': 2, 'portions': {}, 'order': []})
            db.execute('INSERT INTO rooms VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (room_id, number, now, now + WEEK, 'active', 1, self.catalog_hash, settings, member_id, salt, hashed_pin, request_hash))
            db.execute('INSERT INTO members VALUES(?,?,?,?,?,?)',
                       (member_id, room_id, device, nickname, nickname.casefold(), canonical(empty_choices())))
            return self._snapshot(db, self._active(db, room_id), member_id)

    def join(self, data: dict, token: str) -> dict:
        number, nickname, pin = identity(data)
        with self.transaction() as db:
            candidate = db.execute("SELECT * FROM rooms WHERE number=? AND status='active' AND expires>?", (number, self.clock())).fetchone()
        valid = candidate is not None and check_pin(pin, candidate['pin_salt'], candidate['pin_hash'])
        require(valid, '房号或口令不正确，或房间已到期。', 'ROOM_UNAVAILABLE', 404)
        with self.transaction(True) as db:
            device = self._device(db, token)
            room = self._active(db, candidate['id'])
            existing = db.execute('SELECT id FROM members WHERE room_id=? AND device_hash=?', (room['id'], device)).fetchone()
            if existing:
                return self._snapshot(db, room, existing['id'])
            require(db.execute('SELECT count(*) FROM members WHERE room_id=?', (room['id'],)).fetchone()[0] < 24,
                    '房间最多24位参与者。', 'MEMBER_LIMIT', 409)
            require(db.execute('SELECT 1 FROM members WHERE room_id=? AND nickname_key=?', (room['id'], nickname.casefold())).fetchone() is None,
                    '这个昵称已经有人用了，请换一个。', 'NICKNAME_TAKEN', 409)
            member_id = secrets.token_hex(16)
            db.execute('INSERT INTO members VALUES(?,?,?,?,?,?)',
                       (member_id, room['id'], device, nickname, nickname.casefold(), canonical(empty_choices())))
            db.execute('UPDATE rooms SET revision=revision+1 WHERE id=?', (room['id'],))
            room['revision'] += 1
            return self._snapshot(db, room, member_id)

    def snapshot(self, room_id: str, token: str, after: int = -1) -> dict:
        with self.transaction() as db:
            room, member = self._auth(db, room_id, token)
            if after == room['revision']:
                return {'unchanged': True, 'revision': after, 'serverTime': self.clock(), 'expiresAt': room['expires']}
            return self._snapshot(db, room, member['id'])

    def catalog(self, room_id: str, token: str) -> dict:
        with self.transaction() as db:
            room, _ = self._auth(db, room_id, token)
            return self._catalog(db, room['catalog_hash'])

    def operate(self, room_id: str, token: str, operation: dict) -> dict:
        from .mutations import mutate
        op_id = operation.get('id')
        require(isinstance(op_id, str) and OP_ID.fullmatch(op_id) is not None, '操作标识无效。')
        op_hash = digest(canonical(operation))
        with self.transaction(True) as db:
            room, member = self._auth(db, room_id, token)
            old = db.execute('SELECT hash FROM operations WHERE room_id=? AND member_id=? AND op_id=?', (room_id, member['id'], op_id)).fetchone()
            if old:
                require(old['hash'] == op_hash, '不能重复使用不同内容的操作标识。', 'OP_ID_REUSED', 409)
                return {'appliedId': op_id, **self._snapshot(db, room, member['id'])}
            require(db.execute('SELECT count(*) FROM operations WHERE room_id=?', (room_id,)).fetchone()[0] < 50000,
                    '本房间操作已达上限，请导出菜单。', 'OP_LIMIT', 409)
            catalog = self._catalog(db, room['catalog_hash'])
            settings, choices = json.loads(room['settings']), json.loads(member['choices'])
            mutate(operation, settings, choices, member['id'] == room['host'], catalog)
            db.execute('UPDATE members SET choices=? WHERE id=?', (canonical(choices), member['id']))
            merged = aggregate(self._members(db, room_id), settings)
            require(len(merged['selected']) <= 50, '一桌最多50道，请先取消一些选择。', 'MENU_LIMIT', 409)
            settings['order'] = [key for key in settings['order'] if key in merged['selected']]
            room['settings'], room['revision'] = canonical(settings), room['revision'] + 1
            db.execute('UPDATE rooms SET settings=?,revision=? WHERE id=?', (room['settings'], room['revision'], room_id))
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?)', (room_id, member['id'], op_id, op_hash, room['revision']))
            return {'appliedId': op_id, **self._snapshot(db, room, member['id'])}

    def freeze_expired(self, limit=100) -> int:
        with self.transaction(True) as db:
            rows = db.execute("SELECT * FROM rooms WHERE status='active' AND expires<=? ORDER BY expires LIMIT ?", (self.clock(), limit)).fetchall()
            for row in rows:
                room = dict(row)
                payload = canonical(archive_document(room, self._members(db, room['id']), self._catalog(db, room['catalog_hash']))) + '\n'
                db.execute("INSERT INTO archives(room_id,path,payload,hash,status) VALUES(?,?,?,?,'pending')",
                           (room['id'], archive_path(room), payload, digest(payload)))
                db.execute('DELETE FROM members WHERE room_id=?', (room['id'],))
                db.execute("UPDATE rooms SET status='archiving',settings='{}',host='',pin_salt='',pin_hash='',create_hash='' WHERE id=?", (room['id'],))
            db.execute('DELETE FROM devices WHERE expires<=? AND hash NOT IN (SELECT device_hash FROM members)', (self.clock(),))
            return len(rows)

    def claim_archive(self) -> dict | None:
        with self.transaction(True) as db:
            now = self.clock()
            row = db.execute("SELECT * FROM archives WHERE status!='done' AND next_try<=? AND lease_until<=? ORDER BY next_try,room_id LIMIT 1", (now, now)).fetchone()
            if row is None:
                return None
            job, lease = dict(row), secrets.token_hex(16)
            db.execute("UPDATE archives SET status='sending',lease=?,lease_until=?,attempts=attempts+1 WHERE room_id=?", (lease, now + 180, job['room_id']))
            job.update(lease=lease, attempts=job['attempts'] + 1)
            return job

    def finish_archive(self, job: dict, commit_sha: str, blob_sha: str) -> bool:
        require(re_hex(commit_sha) and re_hex(blob_sha), '归档提交标识不合法。')
        with self.transaction(True) as db:
            done = db.execute("UPDATE archives SET status='done',payload=NULL,commit_sha=?,blob_sha=?,completed=?,lease=NULL,lease_until=0,last_error=NULL WHERE room_id=? AND lease=? AND status='sending'",
                              (commit_sha, blob_sha, self.clock(), job['room_id'], job['lease'])).rowcount
            if done:
                db.execute("UPDATE rooms SET status='archived' WHERE id=?", (job['room_id'],))
            return bool(done)

    def fail_archive(self, job: dict, reason: str) -> None:
        delay = min(21600, 30 * (2 ** min(job['attempts'] - 1, 10)))
        with self.transaction(True) as db:
            db.execute("UPDATE archives SET status='pending',next_try=?,lease=NULL,lease_until=0,last_error=? WHERE room_id=? AND lease=?",
                       (self.clock() + delay, reason[:80], job['room_id'], job['lease']))

    def mark_archiver_ok(self):
        with self.transaction(True) as db:
            db.execute("INSERT INTO service_state VALUES('archive-ok',?) ON CONFLICT(name) DO UPDATE SET at=excluded.at", (self.clock(),))

    def archiver_ready(self):
        with self.transaction() as db:
            row = db.execute("SELECT at FROM service_state WHERE name='archive-ok'").fetchone()
            failed = db.execute("SELECT 1 FROM archives WHERE status!='done' AND last_error IS NOT NULL LIMIT 1").fetchone()
            return row is not None and self.clock() - row['at'] < 1800 and failed is None

    def archive_health(self) -> dict:
        with self.transaction() as db:
            now = self.clock()
            row = db.execute("SELECT count(*) AS pending,min(r.expires) AS oldest FROM archives a JOIN rooms r ON r.id=a.room_id WHERE a.status!='done'").fetchone()
            unswept = db.execute("SELECT count(*) FROM rooms WHERE status='active' AND expires<=?", (now,)).fetchone()[0]
            failed = db.execute("SELECT count(*) FROM archives WHERE status!='done' AND last_error IS NOT NULL").fetchone()[0]
            return {'failedJobs': failed, 'pending': row['pending'], 'overdueSeconds': max(0, now - (row['oldest'] or now)), 'unswept': unswept}


def re_hex(value):
    import re
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{40}', value) is not None
