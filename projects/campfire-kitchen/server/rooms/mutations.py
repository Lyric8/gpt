"""Per-member intentions and host-only settings. No whole-room last-write-wins."""
from .domain import canonical, require


def mutate(op, settings, choices, host, catalog):
    kind, key, value, expected = op.get('kind'), op.get('key'), op.get('value'), op.get('expected')
    require(set(op) <= {'id', 'kind', 'key', 'value', 'expected'}, '操作字段不合法。')
    require('expected' in op, '操作缺少原值，请刷新。')
    recipes = {r['id'] for r in catalog['database']['recipes']}
    sets = {'ingredient': ('ingredients', set(catalog['database']['ingredients'])),
            'tool': ('tools', {t['id'] for t in catalog['equipment']['tools']}),
            'vote': ('votes', recipes)}
    if kind in sets:
        field, allowed = sets[kind]
        require(isinstance(key, str) and key in allowed, '此菜谱或物资不属于房间菜谱库。')
        require(type(value) is bool and type(expected) is bool, '勾选值必须是布尔值。')
        current = key in choices[field]
        require(current == expected, '另一个页面刚改过这一项，请核对后再选。', 'CONFLICT', 409)
        values = set(choices[field])
        values.add(key) if value else values.discard(key)
        choices[field] = sorted(values)
        return
    if kind == 'freezer':
        require(type(value) is bool and type(expected) is bool, '冷冻条件必须是布尔值。')
        require(choices['hasFreezer'] == expected, '冷冻条件已变，请重新核对。', 'CONFLICT', 409)
        choices['hasFreezer'] = value
        return
    require(host, '人数、份量和出餐顺序由房主统一调整。', 'HOST_REQUIRED', 403)
    if kind == 'people':
        require(type(value) is int and 1 <= value <= 16 and type(expected) is int, '用餐人数为1—16人。')
        current = settings['people']
    elif kind == 'portion':
        require(isinstance(key, str) and key in recipes, '菜谱不存在。')
        require(type(value) in (int, float) and value in (0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4), '请选择有效份量。')
        require(type(expected) in (int, float), '原份量无效。')
        current = settings['portions'].get(key, 1)
    elif kind == 'order':
        require(isinstance(value, list) and len(value) <= 50 and all(isinstance(x, str) and x in recipes for x in value), '顺序中的菜谱无效。')
        require(len(set(value)) == len(value) and isinstance(expected, list), '顺序不得重复。')
        current = settings['order']
    else:
        require(False, '不支持的房间操作。')
    require(canonical(current) == canonical(expected), '这项设置已在另一个页面改变，请核对后重试。', 'CONFLICT', 409)
    if kind == 'portion':
        settings['portions'][key] = value
    else:
        settings[kind] = value
