/** Pure catalog, quantity and menu engine. No network, DOM or storage dependency. */
export const APP_ID = 'campfire-kitchen';
export const STATE_VERSION = 2;
export const LIMITS = Object.freeze({ recipes: 500, ingredients: 1000, sources: 500, fileBytes: 5000000, people: 16 });
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const plain = o => o !== null && typeof o === 'object' && !Array.isArray(o);
const finite = n => typeof n === 'number' && Number.isFinite(n);
const idOK = s => typeof s === 'string' && /^[A-Za-z][A-Za-z0-9-]{0,79}$/.test(s) && !['constructor', 'prototype', '__proto__'].includes(s);
const str = (s, n = 3000) => typeof s === 'string' && s.length <= n;
const txt = (s, n = 3000) => typeof s === 'string' ? s.slice(0, n) : '';
const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
const unique = a => [...new Set(a)];
const units = new Set(['g', 'ml', 'tsp', '个', '张']);
export function safeUrl(value) { try {
    const u = new URL(value);
    return ['https:', 'http:'].includes(u.protocol) && !u.username && !u.password ? u.href : '';
}
catch {
    return '';
} }
export function escapeHTML(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
export function roundNumber(n, places = 4) { return Number(n.toFixed(places)); }
export function formatQty(n, unit) {
    if (!finite(n))
        return '—';
    if (unit === 'tsp') {
        const parts = [[1 / 16, '1/16'], [1 / 8, '⅛'], [1 / 4, '¼'], [3 / 8, '⅜'], [1 / 2, '½'], [5 / 8, '⅝'], [3 / 4, '¾'], [7 / 8, '⅞']];
        const whole = Math.floor(n + 1e-10), fraction = n - whole, hit = parts.find(([x]) => Math.abs(fraction - x) < 1e-7);
        return `${hit ? `${whole || ''}${hit[1]}` : roundNumber(n, 3)} 茶匙`;
    }
    return `${roundNumber(n, 3)} ${unit}`;
}
function signature(value) {
    const s = typeof value === 'string' ? value : JSON.stringify(value);
    let h = 2166136261;
    for (let j = 0; j < s.length; j++) {
        h ^= s.charCodeAt(j);
        h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36);
}
export function validateDatabase(db) {
    const errors = [], err = s => { if (errors.length < 100)
        errors.push(s); };
    if (!plain(db) || db.schemaVersion !== 2)
        return { ok: false, errors: ['菜谱库 schemaVersion 必须为2；旧版菜单可通过「导入备份」迁移，不导入旧鲜干菜谱库。'] };
    if (!plain(db.ingredients) || !plain(db.sources) || !Array.isArray(db.recipes))
        return { ok: false, errors: ['缺少 ingredients、sources 或 recipes。'] };
    if (Object.keys(db.ingredients).length > LIMITS.ingredients || db.recipes.length > LIMITS.recipes || Object.keys(db.sources).length > LIMITS.sources || !db.recipes.length)
        err('菜谱库数量超限或为空。');
    for (const k of ['title', 'version', 'updated'])
        if (!str(db[k], 200) || !db[k])
            err(`库的${k}无效。`);
    const purchases = new Map();
    for (const [id, i] of Object.entries(db.ingredients)) {
        if (!idOK(id) || !plain(i)) {
            err(`原料ID无效：${id}`);
            continue;
        }
        if (!str(i.name, 150) || !i.name || !units.has(i.unit) || !str(i.group, 60) || !str(i.storage, 250) || !str(i.note, 2000))
            err(`原料字段不完整：${id}`);
        if (!Array.isArray(i.allergens) || i.allergens.length > 30 || !i.allergens.every(a => str(a, 100)))
            err(`过敏原字段无效：${id}`);
        if (i.freshHerb !== undefined && typeof i.freshHerb !== 'boolean')
            err(`freshHerb必须布尔值：${id}`);
        if (i.purchase) {
            const p = i.purchase;
            if (!plain(p) || !idOK(p.id) || !str(p.name, 150) || !units.has(p.unit) || !['sum', 'max'].includes(p.method) || !finite(p.yield) || p.yield <= 0 || !finite(p.roundTo) || p.roundTo <= 0 || !str(p.note, 1000))
                err(`采购换算无效：${id}`);
            else {
                const prior = purchases.get(p.id);
                const config = JSON.stringify([p.name, p.unit, p.method, p.roundTo]);
                if (prior && prior !== config)
                    err(`同一采购项的规则冲突：${p.id}`);
                purchases.set(p.id, config);
            }
        }
    }
    for (const [id, s] of Object.entries(db.sources))
        if (!idOK(id) || !plain(s) || !str(s.title, 300) || !safeUrl(s.url) || !str(s.scope, 1500))
            err(`来源字段无效：${id}`);
    const seen = new Set();
    for (const r of db.recipes) {
        if (!plain(r) || !idOK(r.id) || seen.has(r.id)) {
            err('菜谱ID不合法或重复。');
            continue;
        }
        seen.add(r.id);
        for (const k of ['needsFreezer', 'rich', 'light'])
            if (typeof r[k] !== 'boolean')
                err(`${r.id}：${k}必须为布尔值。`);
        if (own(r, 'choices'))
            err(`${r.id}：v2菜谱必须定稿，不再允许choices。`);
        for (const k of ['title', 'category', 'tip', 'smoke', 'fun', 'technique', 'difficulty', 'origin', 'cleanup', 'batchNote', 'profile', 'taste', 'texture', 'textureFamily', 'moment', 'why', 'hold', 'main', 'interaction'])
            if (!str(r[k], 4000) || !r[k])
                err(`${r.id}：缺少${k}。`);
        for (const k of ['basePeople', 'revision', 'batchFactor'])
            if (!finite(r[k]) || r[k] <= 0 || r[k] > 100)
                err(`${r.id}：${k}无效。`);
        for (const k of ['activeMinutes', 'totalMinutes', 'homeMinutes', 'rank'])
            if (!finite(r[k]) || r[k] < 0 || r[k] > 1440)
                err(`${r.id}：${k}无效。`);
        if (r.activeMinutes > r.totalMinutes)
            err(`${r.id}：主动操作不能超过总耗时。`);
        for (const k of ['steps', 'prep', 'decisions', 'equipment', 'sources', 'tags'])
            if (!Array.isArray(r[k]) || r[k].length > 100 || !r[k].every(x => str(x, 5000)))
                err(`${r.id}：${k}必须是有界文本数组。`);
        if (!Array.isArray(r.steps) || !r.steps.length || !Array.isArray(r.prep) || !Array.isArray(r.sources) || !Array.isArray(r.ingredients) || !r.ingredients.length || r.ingredients.length > 100) {
            err(`${r.id}：缺少材料/步骤/来源。`);
            continue;
        }
        if (!r.sources.length || r.sources.some(id => !own(db.sources, id)))
            err(`${r.id}：来源不存在。`);
        const keys = new Set();
        for (const a of r.ingredients) {
            if (!plain(a) || !idOK(a.key) || keys.has(a.key) || !own(db.ingredients, a.ingredient) || !finite(a.qty) || a.qty <= 0 || a.qty > 100000 || !['在家', '现场'].includes(a.stage) || !['linear', 'batch'].includes(a.scaling) || !str(a.form, 1000) || !str(a.pack, 150)) {
                err(`${r.id}：材料行无效或key重复。`);
                continue;
            }
            if (own(a, 'optional'))
                err(`${r.id}：材料不再留optional开关。`);
            keys.add(a.key);
        }
        for (const s of [...r.steps, ...r.prep])
            if (typeof s === 'string')
                for (const m of s.matchAll(/\{\{([^{}]+)\}\}/g))
                    if (!keys.has(m[1]))
                        err(`${r.id}：步骤引用不存在的材料${m[1]}。`);
    }
    for (const k of ['presets', 'herbGuide', 'safety', 'principles', 'audit'])
        if (!Array.isArray(db[k]) || db[k].length > 1000)
            err(`缺少${k}数组或超限。`);
    if (errors.length)
        return { ok: false, errors };
    const presetIds = new Set();
    for (const p of db.presets) {
        if (!plain(p) || !idOK(p.id) || presetIds.has(p.id) || !str(p.name, 150) || !str(p.note, 1500) || !plain(p.selected) || Object.keys(p.selected).length > 50 || Object.entries(p.selected).some(([id, n]) => !seen.has(id) || !finite(n) || n < .25 || n > 4))
            err('预设菜单字段无效。');
        else
            presetIds.add(p.id);
    }
    for (const h of db.herbGuide)
        if (!plain(h) || !str(h.name, 150) || !str(h.decision, 3000) || !str(h.why, 3000) || !Array.isArray(h.recipes) || h.recipes.some(id => !seen.has(id)) || !Array.isArray(h.sources) || h.sources.some(id => !own(db.sources, id)))
            err('材料裁决字段无效。');
    for (const s of db.safety)
        if (!plain(s) || !str(s.title, 150) || !str(s.text, 4000) || !Array.isArray(s.sources) || s.sources.some(id => !own(db.sources, id)))
            err('安全说明字段无效。');
    if (!db.principles.every(s => str(s, 4000)))
        err('原则字段无效。');
    for (const a of db.audit)
        if (!plain(a) || !idOK(a.oldId) || !str(a.oldTitle, 300) || !str(a.status, 100) || !str(a.reason, 3000) || a.newId !== null && !seen.has(a.newId))
            err('逐菜审查记录无效。');
    if (db.migration) {
        const m = db.migration;
        if (!plain(m) || !plain(m.retired) || !Array.isArray(m.rewritten) || m.rewritten.some(id => !seen.has(id)))
            err('迁移规则无效。');
        else
            for (const [id, x] of Object.entries(m.retired))
                if (!idOK(id) || !plain(x) || !str(x.title, 300) || !str(x.reason, 2000) || !seen.has(x.suggestedId))
                    err('退役映射无效。');
    }
    return { ok: !errors.length, errors };
}
export function defaultState() { return { app: APP_ID, stateVersion: 2, people: 2, selected: [], portions: {}, order: [], checked: {}, steps: {}, notes: {}, menuName: '我的这一顿', hasFreezer: false, history: [], timer: null }; }
export function sanitizeState(raw, db) {
    const s = defaultState();
    if (!plain(raw))
        return s;
    const ids = new Set(db.recipes.map(r => r.id));
    if (finite(raw.people))
        s.people = clamp(Math.round(raw.people), 1, LIMITS.people);
    s.menuName = txt(raw.menuName, 100) || s.menuName;
    s.hasFreezer = raw.hasFreezer === true;
    if (Array.isArray(raw.selected))
        s.selected = unique(raw.selected.filter(id => ids.has(id))).slice(0, 50);
    if (plain(raw.portions))
        for (const [id, n] of Object.entries(raw.portions))
            if (ids.has(id) && finite(n))
                s.portions[id] = clamp(n, .25, 4);
    if (Array.isArray(raw.order))
        s.order = unique(raw.order.filter(id => s.selected.includes(id)));
    for (const field of ['checked', 'steps'])
        if (plain(raw[field]))
            for (const [k, v] of Object.entries(raw[field]).slice(0, 5000))
                if (str(k, 350) && !['__proto__', 'constructor', 'prototype'].includes(k) && str(v, 100))
                    s[field][k] = v;
    if (plain(raw.notes))
        for (const [id, n] of Object.entries(raw.notes))
            if (ids.has(id) && str(n, 10000))
                s.notes[id] = n.slice(0, 3000);
    if (Array.isArray(raw.history))
        s.history = raw.history.slice(-30).filter(h => plain(h) && str(h.at, 100) && str(h.name, 100) && Array.isArray(h.ids)).map(h => ({ at: h.at, name: h.name, ids: unique(h.ids.filter(id => ids.has(id))).slice(0, 50) }));
    if (plain(raw.timer) && finite(raw.timer.endsAt) && raw.timer.endsAt > 0 && str(raw.timer.label, 200))
        s.timer = { endsAt: raw.timer.endsAt, label: raw.timer.label };
    return s;
}
export function recipeView(db, id, state, portionOverride) {
    const r = db.recipes.find(r => r.id === id);
    if (!r)
        throw new Error('找不到菜谱：' + id);
    const portion = finite(portionOverride) ? clamp(portionOverride, .25, 4) : (state.portions[id] ?? 1), scale = state.people / r.basePeople * portion;
    const batches = Math.max(1, Math.ceil(scale / r.batchFactor - 1e-10));
    const rows = r.ingredients.map(a => ({ ...a, ...db.ingredients[a.ingredient], key: a.key, ingredient: a.ingredient, qty: roundNumber(a.qty * (a.scaling === 'batch' ? batches : scale)), baseQty: a.qty, pack: a.pack, stage: a.stage, form: a.form, scaling: a.scaling }));
    const byKey = Object.fromEntries(rows.map(a => [a.key, a]));
    const template = t => t.replace(/\{\{([^{}]+)\}\}/g, (_, k) => byKey[k] ? formatQty(byKey[k].qty, byKey[k].unit) : '[材料缺失]');
    const hash = signature([db.version, r.id, r.revision, scale, rows.map(a => [a.key, a.qty, a.form]), r.steps, r.prep]);
    return { ...r, portion, scale, batches, rows, steps: r.steps.map(template), prep: r.prep.map(template), activeEstimate: r.activeMinutes * batches, totalEstimate: r.totalMinutes * batches, homeEstimate: r.homeMinutes * batches, signature: hash };
}
export function selectedViews(db, state) {
    const all = state.selected.map(id => recipeView(db, id, state));
    const rank = new Map(state.order.map((id, i) => [id, i]));
    return all.sort((a, b) => state.order.length ? ((rank.get(a.id) ?? 10000 + a.rank) - (rank.get(b.id) ?? 10000 + b.rank)) : (a.rank - b.rank || state.selected.indexOf(a.id) - state.selected.indexOf(b.id)));
}
export function buildPlan(db, state) {
    const views = selectedViews(db, state), shop = new Map(), packs = [], equipment = new Set(), sources = new Set(), allergens = new Set();
    for (const r of views) {
        const grouped = new Map();
        for (const a of r.rows) {
            if (!shop.has(a.ingredient))
                shop.set(a.ingredient, { id: a.ingredient, name: a.name, unit: a.unit, group: a.group, qty: 0, storage: a.storage, note: a.note, pantryHint: a.pantryHint === true, uses: [], purchase: a.purchase });
            const item = shop.get(a.ingredient);
            item.qty = roundNumber(item.qty + a.qty);
            item.uses.push({ recipeId: r.id, title: r.title, qty: a.qty, unit: a.unit, form: a.form, stage: a.stage, pack: a.pack, scaling: a.scaling });
            const k = a.pack;
            if (!grouped.has(k))
                grouped.set(k, []);
            grouped.get(k).push(a);
            for (const x of a.allergens ?? [])
                allergens.add(x);
        }
        for (const [name, rows] of grouped)
            packs.push({ id: r.id + ':' + name, recipeId: r.id, title: r.title, name, rows, signature: signature([r.signature, name, rows.map(a => [a.key, a.qty])]) });
        for (const x of r.equipment)
            equipment.add(x);
        for (const x of r.sources)
            sources.add(x);
    }
    const shopping = [...shop.values()].sort((a, b) => a.group.localeCompare(b.group, 'zh') || a.name.localeCompare(b.name, 'zh'));
    for (const item of shopping)
        item.signature = signature([item.id, item.qty, item.unit, item.uses]);
    const pmap = new Map();
    for (const item of shopping)
        if (item.purchase) {
            const p = item.purchase;
            if (!pmap.has(p.id))
                pmap.set(p.id, { ...p, raw: 0, components: [] });
            const v = pmap.get(p.id), amount = item.qty / p.yield;
            v.raw = p.method === 'sum' ? v.raw + amount : Math.max(v.raw, amount);
            v.components.push({ name: item.name, qty: item.qty, unit: item.unit, note: p.note });
        }
    const procurement = [...pmap.values()].map(p => ({ ...p, qty: roundNumber(Math.ceil((p.raw - 1e-9) / p.roundTo) * p.roundTo) }));
    let minute = 0;
    const schedule = views.map(r => { const start = minute; minute += r.totalEstimate; return { recipeId: r.id, title: r.title, start, end: minute, active: r.activeEstimate, batches: r.batches, hold: r.hold, technique: r.technique }; });
    const metrics = { count: views.length, profiles: unique(views.map(r => r.profile)).length, textures: unique(views.map(r => r.textureFamily)).length, techniques: unique(views.map(r => r.technique)).length, active: views.reduce((n, r) => n + r.activeEstimate, 0), sequential: minute, home: Math.ceil(views.reduce((n, r) => n + r.homeEstimate, 0)), freshHerbs: shopping.filter(x => db.ingredients[x.id].freshHerb).map(x => x.name) };
    const evaluation = reviewMenu(db, state, views, shopping, metrics);
    return { views, shopping, procurement, packs, equipment: [...equipment].sort(), sources: [...sources], allergens: [...allergens].sort(), schedule, metrics, ...evaluation };
}
export function reviewMenu(db, state, views, shopping, metrics) {
    const issues = [], add = (level, title, detail, kind) => issues.push({ level, title, detail, kind });
    const mapBy = key => { const m = new Map(); for (const r of views) {
        const k = r[key];
        if (!m.has(k))
            m.set(k, []);
        m.get(k).push(r);
    } return m; };
    if (!views.length)
        return { issues: [], suggestions: [] };
    if (views.some(r => r.needsFreezer) && !state.hasFreezer)
        add('danger', '菜单需要持续冷冻', '选中了冰淇淋。确认有持续≤-18℃冷冻条件；普通冷藏不够，程序不会偷偷改成酸奶。', 'freezer');
    for (const [k, rs] of mapBy('profile'))
        if (rs.length > 1)
            add('note', `「${k}」出现${rs.length}次`, rs.map(r => r.title).join('、') + '。喜欢这个味可以保留；想求新，把其中一道换成不同味型。', 'profile');
    for (const [k, rs] of mapBy('textureFamily'))
        if (rs.length >= 3)
            add('note', `「${k}」口感重复${rs.length}次`, rs.map(r => r.title).join('、') + '。虽然调味不同，咀嚼与动作结构接近；考虑把一道换成汤、手卷或冷热对比。', 'texture');
    for (const [k, rs] of mapBy('main'))
        if (rs.length > 1) {
            const sum = rs.reduce((n, r) => n + r.portion, 0);
            add('note', `同主材：${rs.map(r => r.title).join(' / ')}`, `当前共${roundNumber(sum, 2)}份基准量。做对比时可各半份，材料会据实加总；不会擅自把两菜合成一份。`, 'main');
        }
    if (metrics.active > 65)
        add('warn', '主厨可能一直站着', `估计主动操作${metrics.active}分钟（不含家里预制）。建议留一项主打动作，再搭冷菜、提前做酱的快手菜；不用一次做完所有想吃的。`, 'workload');
    if (views.filter(r => r.rich).length >= 3)
        add('warn', '浓味/奶酪类偏多', '这顿有至少3道浓酱或奶酪甜品。换一项为清鲜汤、冷米纸卷、柑橘蔬菜，有利于拉开口感。', 'rich');
    if (views.length >= 4 && !views.some(r => r.light))
        add('note', '缺一口清爽缓冲', '当前以热浓味为主。加入一份鲜酸冷菜或清汤，不用每轮都继续加奶香和焦壳。', 'light');
    if (metrics.freshHerbs.length >= 4)
        add('note', '鲜叶采购略分散', `当前要带${metrics.freshHerbs.length}种鲜叶：${metrics.freshHerbs.join('、')}。不是让你改配方；不想带这么多时换一道菜即可。`, 'herbs');
    if (state.people > 4)
        add('note', '多人要按批，不加厚', '量表已放大，时间按整批保守计。炭炉实际可用面积未测；不要把全部食材铺满、影响通风或下锅后降温。', 'batches');
    if (views.length > 7)
        add('warn', '这顿菜数偏多', '超过7道小份也会增加称量、火面切换与等候。勾选代表本次要做，收藏体验请写笔记/用菜谱库，不必全做。', 'count');
    const texture = new Set(views.map(r => r.textureFamily)), taste = new Set(views.map(r => r.profile)), main = new Set(views.map(r => r.main)), tech = new Set(views.map(r => r.technique)), owned = new Set(shopping.map(i => i.id)), history = new Set(state.history.slice(-3).flatMap(h => h.ids));
    const wantsLight = issues.some(x => ['rich', 'light'].includes(x.kind));
    const candidates = db.recipes.filter(r => !state.selected.includes(r.id) && (!r.needsFreezer || state.hasFreezer)).map(r => {
        const ids = unique(r.ingredients.map(a => a.ingredient));
        let novelty = 0;
        const reasons = [];
        if (!texture.has(r.textureFamily)) {
            novelty += 2;
            reasons.push(`换成${r.textureFamily}`);
        }
        if (!taste.has(r.profile)) {
            novelty += 4;
            reasons.push(`新增${r.profile}`);
        }
        else
            novelty -= 3;
        if (!main.has(r.main))
            novelty += 1;
        else
            novelty -= 2;
        if (!tech.has(r.technique)) {
            novelty += 2;
            reasons.push(`${r.technique}换一下做法`);
        }
        if (wantsLight && r.light) {
            novelty += 4;
            reasons.push('给浓味留一口清爽');
        }
        if (metrics.active > 65 && r.activeMinutes <= 6) {
            novelty += 3;
            reasons.push('现场主动操作较少');
        }
        if (history.has(r.id))
            novelty -= 3;
        const extras = ids.filter(id => !owned.has(id) && !db.ingredients[id].pantryHint && id !== 'water').length;
        novelty -= extras * .22;
        if (!reasons.length)
            reasons.push('另一个口感方向');
        return { id: r.id, title: r.title, reasons: reasons.slice(0, 2), extraIngredients: extras, score: novelty };
    }).sort((a, b) => b.score - a.score || a.extraIngredients - b.extraIngredients || a.id.localeCompare(b.id));
    return { issues, suggestions: candidates.slice(0, 3) };
}
export function applyPreset(db, state, presetId) { const p = db.presets.find(p => p.id === presetId); if (!p)
    throw new Error('菜单不存在'); const s = sanitizeState(state, db); s.selected = Object.keys(p.selected); s.portions = { ...p.selected }; s.order = []; s.checked = {}; s.steps = {}; s.menuName = p.name; return s; }
export function makeBackup(db, state) { return { app: APP_ID, backupVersion: 2, exportedAt: new Date().toISOString(), catalogVersion: db.version, database: db, state: sanitizeState(state, db) }; }
export function importBackup(input, db) {
    if (!plain(input) || input.app !== APP_ID || ![1, 2].includes(input.backupVersion) || !plain(input.state))
        throw new Error('不是支持的火边菜单备份（backupVersion 1或2）。');
    const warnings = [];
    if (input.backupVersion === 2 && input.database !== undefined) {
        const check = validateDatabase(input.database);
        if (!check.ok)
            throw new Error('备份中的菜谱库无效：' + check.errors.slice(0, 3).join('；'));
        db = input.database;
    }
    const raw = input.state, known = new Set(db.recipes.map(r => r.id));
    for (const id of Array.isArray(raw.selected) ? raw.selected : [])
        if (!known.has(id))
            warnings.push(`未导入已退役/未知菜：${db.migration?.retired?.[id]?.title ?? String(id)}。未自动替换。`);
    if (input.backupVersion === 1) {
        const adapted = { ...raw, portions: {}, checked: {}, steps: {}, order: [] };
        for (const [id, c] of Object.entries(plain(raw.configs) ? raw.configs : {}))
            if (known.has(id) && plain(c) && finite(c.portion))
                adapted.portions[id] = c.portion;
        warnings.unshift('已保留选菜、人数、份量和笔记；鲜干开关及旧打勾进度清空，统一使用v2定稿配方。');
        for (const id of Array.isArray(raw.selected) ? raw.selected : [])
            if (db.migration?.rewritten?.includes(id))
                warnings.push(`请重新查看「${db.recipes.find(r => r.id === id).title}」：这道做法已实质重写。`);
        return { database: db, state: sanitizeState(adapted, db), warnings };
    }
    return { database: db, state: sanitizeState(raw, db), warnings };
}
export function makeMarkdown(db, state) {
    const p = buildPlan(db, state), lines = [`# ${state.menuName}`, `\n${state.people}人｜火边 ${db.version}｜${p.views.length}道小份\n`, `> 配方定稿，不切换鲜干。分钟仅为检查起点；食物以安全中心温度为准。\n`];
    if (p.issues.length) {
        lines.push('## 先看这顿是否舒服');
        for (const x of p.issues)
            lines.push(`- **${x.title}**：${x.detail}`);
    }
    if (p.procurement.length) {
        lines.push('\n## 采购折算（不是额外材料）');
        for (const x of p.procurement)
            lines.push(`- ${x.name}：约${formatQty(x.qty, x.unit)}。${x.components.map(c => `${c.name}${formatQty(c.qty, c.unit)}`).join(' + ')}；${x.note}`);
    }
    lines.push('\n## 食材净用量（同原料已合并）', '\n| 材料 | 用量 | 保存／说明 |', '|---|---:|---|');
    const md = s => String(s).replace(/\|/g, '／').replace(/\r?\n/g, ' ');
    for (const x of p.shopping)
        lines.push(`| ${md(x.name)} | ${formatQty(x.qty, x.unit)} | ${md(x.storage)}；${md(x.note)} |`);
    lines.push('\n> 烹调用水已计；洗手、洗菜、洗工具、米饭煮制及临时补水不混成配方用量，请另带充足饮用水。茶匙是5ml量勺，不能换算成同等克数。');
    lines.push('\n## 在家任务与按菜分装');
    for (const r of p.views) {
        lines.push(`\n### ${r.title}`);
        for (const t of r.prep)
            lines.push(`- [ ] ${t}`);
        for (const pack of p.packs.filter(x => x.recipeId === r.id))
            lines.push(`- [ ] **${pack.name}**：${pack.rows.map(a => `${a.name}${formatQty(a.qty, a.unit)}（${a.form}${a.scaling === 'batch' ? '；每批用量已保留' : ''}）`).join('；')}`);
    }
    lines.push('\n## 到场顺序（默认逐道，不承诺并行）');
    for (const x of p.schedule)
        lines.push(`- ${x.start}～${x.end}分钟：${x.title}，${x.technique}，${x.batches}批；${x.hold}`);
    lines.push('\n## 现场操作卡');
    for (const r of p.views) {
        lines.push(`\n### ${r.title} · ${r.portion}份 × ${state.people}人`, `\n${r.taste}｜${r.texture}｜${r.moment}`, `\n**这一道玩什么：**${r.fun}`, `\n**定稿理由：**${r.decisions.join(' ')}`, `\n**本菜量表：**${r.rows.map(a => `${a.name}${formatQty(a.qty, a.unit)}（${a.form}）`).join('；')}`);
        r.steps.forEach((t, j) => lines.push(`${j + 1}. ${t}`));
        lines.push(`\n**防翻车：**${r.tip}`, `\n工具：${r.equipment.join('、')}`);
        if (state.notes[r.id])
            lines.push(`\n笔记：${state.notes[r.id]}`);
        lines.push(`\n依据：${r.sources.map(id => `[${db.sources[id].title}](${db.sources[id].url})`).join('；')}`);
    }
    lines.push('\n## 工具并集', p.equipment.join('、'), '\n## 安全与保存');
    for (const s of db.safety)
        lines.push(`- **${s.title}**：${s.text}`);
    lines.push('\n## 菜谱研究边界', '经典来源核对用于技法和组合；此处用量为两人小份改编，不是已在你的炉具上试吃或实测。所有食材过敏原仍以商品标签为准。');
    return lines.join('\n') + '\n';
}
export function makeCSV(db, state) {
    const rows = [['材料', '净用量', '单位', '所属菜', '该菜用量', '处理形态', '分装组', '保存', '说明']];
    for (const x of buildPlan(db, state).shopping)
        for (const u of x.uses)
            rows.push([x.name, x.qty, x.unit, u.title, u.qty, u.form, u.pack, x.storage, x.note]);
    const cell = v => '"' + String(v).replace(/^[=+\-@]/, m => "'" + m).replace(/"/g, '""') + '"';
    return '\ufeff' + rows.map(r => r.map(cell).join(',')).join('\r\n') + '\r\n';
}
export function checkKey(kind, id) { return kind + ':' + id; }
export function isChecked(state, kind, id, hash) { return (kind === 'step' ? state.steps : state.checked)[checkKey(kind, id)] === hash; }
export function setChecked(state, kind, id, hash, checked) { const dest = kind === 'step' ? state.steps : state.checked, k = checkKey(kind, id); if (checked)
    dest[k] = hash;
else
    delete dest[k]; }
