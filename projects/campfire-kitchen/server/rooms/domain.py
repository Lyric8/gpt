"""Room protocol validation and deterministic aggregation; no I/O."""
from __future__ import annotations
import hashlib
import hmac
import json
import math
import re
import secrets
import unicodedata
from datetime import datetime, timezone

WEEK = 7 * 24 * 60 * 60
POLICY = 'aggregate-public-v1'
NUMBER = re.compile(r'^[0-9]{4,12}$')
INSTANCE = re.compile(r'^[a-f0-9]{32}$')
OP_ID = re.compile(r'^[a-f0-9-]{32,36}$')


class Problem(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message
        super().__init__(code)


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def require(condition: bool, message: str, code: str = 'INVALID_INPUT', status: int = 400) -> None:
    if not condition:
        raise Problem(status, code, message)


def identity(data: dict) -> tuple[str, str, str]:
    number, nickname, pin = data.get('number'), data.get('nickname'), data.get('passcode', '')
    require(isinstance(number, str) and NUMBER.fullmatch(number) is not None, '房号请输入4—12位数字，保留开头的0。')
    require(isinstance(nickname, str), '请填写房间昵称。')
    nickname = ' '.join(unicodedata.normalize('NFKC', nickname).split())
    require(1 <= len(nickname) <= 16 and not any(unicodedata.category(c).startswith('C') for c in nickname), '昵称需要1—16个可见字符。')
    require(isinstance(pin, str) and (not pin or re.fullmatch(r'[0-9]{4,8}', pin) is not None), '口令留空或填写4—8位数字。')
    require(data.get('archivePolicy') == POLICY, '请刷新页面，阅读房间的七天归档说明。', 'POLICY_REQUIRED')
    return number, nickname, pin


def pin_hash(pin: str, salt: str) -> str:
    return hashlib.scrypt(pin.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32).hex()


def encode_pin(pin: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, pin_hash(pin, salt) if pin else ''


def check_pin(pin: str, salt: str, expected: str) -> bool:
    return not expected or hmac.compare_digest(pin_hash(pin, salt), expected)


def empty_choices() -> dict:
    return {'ingredients': [], 'tools': [], 'votes': [], 'hasFreezer': False}


def aggregate(members: list[dict], settings: dict) -> dict:
    all_votes = set().union(*(set(m['choices']['votes']) for m in members))
    selected = [key for key in settings['order'] if key in all_votes]
    selected += sorted(all_votes - set(selected))
    return {
        'selected': selected,
        'inventory': {kind: sorted(set().union(*(set(m['choices'][kind]) for m in members))) for kind in ('ingredients', 'tools')},
        'hasFreezer': any(m['choices']['hasFreezer'] for m in members),
    }


def archive_document(room: dict, members: list[dict], catalog: dict) -> dict:
    """Allowlist only. Never copy room/member rows, secrets, names, tokens or operation logs."""
    settings = json.loads(room['settings'])
    merged = aggregate(members, settings)
    selected = set(merged['selected'])
    recipes = [r for r in catalog['database']['recipes'] if r['id'] in selected]
    ids = {a['ingredient'] for r in recipes for a in r['ingredients']}
    sources = {s for r in recipes for s in r['sources']}
    quantities: dict[str, float] = {}
    for recipe in recipes:
        scale = settings['people'] / recipe['basePeople'] * settings['portions'].get(recipe['id'], 1)
        batches = max(1, math.ceil(scale / recipe['batchFactor'] - 1e-10))
        for item in recipe['ingredients']:
            q = item['qty'] * (batches if item['scaling'] == 'batch' else scale)
            key = item['ingredient']
            quantities[key] = round(quantities.get(key, 0) + q, 4)
    return {
        'schemaVersion': 1, 'archivePolicy': POLICY, 'roomNumber': room['number'],
        'roomInstance': room['id'], 'createdAt': room['created'], 'closedAt': room['expires'],
        'catalogHash': room['catalog_hash'], 'catalogVersion': catalog['database']['version'],
        'participantCount': len(members), 'revision': room['revision'],
        'menu': {'people': settings['people'], 'selected': merged['selected'],
                 'portions': {key: settings['portions'].get(key, 1) for key in merged['selected']}},
        'inventory': merged['inventory'], 'hasFreezer': merged['hasFreezer'],
        'netQuantities': quantities,
        'catalogSnapshot': {'recipes': recipes,
                            'ingredients': {i: catalog['database']['ingredients'][i] for i in sorted(ids | set(merged['inventory']['ingredients']))},
                            'sources': {i: catalog['database']['sources'][i] for i in sorted(sources)},
                            'equipment': catalog['equipment']},
    }


def archive_path(room: dict) -> str:
    month = datetime.fromtimestamp(room['expires'], timezone.utc).strftime('%Y/%m')
    return f'rooms/{month}/{room["id"]}.json'
