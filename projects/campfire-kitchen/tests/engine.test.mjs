import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { validateDatabase, defaultState, sanitizeState, recipeView, buildPlan, applyPreset, formatQty, escapeHTML, safeUrl, makeBackup, importBackup, makeMarkdown, makeCSV, isChecked, setChecked } from '../src/engine.mjs';
const db = JSON.parse(fs.readFileSync(new URL('../data/recipes.json', import.meta.url), 'utf8'));
const clone = x => JSON.parse(JSON.stringify(x));
const state = (ids, portions = {}, people = 2) => ({ ...defaultState(), selected: ids, portions, people });
const row = (p, id) => p.shopping.find(x => x.id === id);
const invalid = (name, mutate) => test(name, () => { const d = clone(db); mutate(d); assert.equal(validateDatabase(d).ok, false); });
test('内置库：50道、40条旧菜审查、8套菜单、无鲜干选择', () => { assert.deepEqual(validateDatabase(db), { ok: true, errors: [] }); assert.equal(db.recipes.length, 50); assert.equal(db.audit.length, 40); assert.equal(db.presets.length, 8); assert.equal(db.audit.filter(x => x.status === '合并退役').length, 5); assert(db.recipes.every(r => !('choices' in r) && r.ingredients.every(a => !('optional' in a)))); });
for (const r of db.recipes)
    test(`定稿卡完整与多倍率一致：${r.id}`, () => {
        assert(r.decisions.length > 0);
        assert(r.why.length > 10);
        assert(r.fun.length > 10);
        assert(r.sources.length > 0);
        for (const people of [1, 2, 4, 16])
            for (const portion of [.25, .5, .75, 1, 2, 4]) {
                const s = state([r.id], { [r.id]: portion }, people), v = recipeView(db, r.id, s), p = buildPlan(db, s);
                assert(v.rows.length === r.ingredients.length);
                assert(v.rows.every(a => a.qty > 0 && Number.isFinite(a.qty)));
                assert(!v.steps.some(t => t.includes('{{')));
                assert(!v.prep.some(t => t.includes('{{')));
                for (const a of v.rows) {
                    assert(row(p, a.ingredient));
                    assert(Math.abs(a.qty - a.baseQty * (a.scaling === 'batch' ? v.batches : v.scale)) < .00011);
                }
                assert(p.schedule[0].end === v.totalEstimate);
                assert(p.metrics.active >= r.activeMinutes);
            }
    });
test('两种牛肉各半份精确合计220g、不重复采购', () => { const p = buildPlan(db, state(['rosemary-beef', 'chimi-beef'], { 'rosemary-beef': .5, 'chimi-beef': .5 })); assert.equal(row(p, 'beef').qty, 220); assert.equal(row(p, 'beef').uses.length, 2); assert.equal(row(p, 'rosemaryFresh').qty, .5); assert.equal(row(p, 'parsleyFresh').qty, 4); assert.equal(row(p, 'oreganoDry').qty, .0625); });
test('同样原料不同形态按用途保留、包不混成一袋', () => { const p = buildPlan(db, state(['rosemary-beef', 'paprika-shrimp', 'scallop-vermicelli'])); assert.equal(row(p, 'garlic').qty, 25); assert.equal(new Set(row(p, 'garlic').uses.map(u => u.form)).size, 3); assert(p.packs.some(x => x.name.includes('生食'))); assert(p.packs.every(x => x.recipeId)); });
test('鲜欧芹与干牛至同菜共存，不是全局fresh模式', () => { const v = recipeView(db, 'chimi-beef', state(['chimi-beef'])); assert(v.rows.some(a => a.ingredient === 'parsleyFresh')); assert(v.rows.some(a => a.ingredient === 'oreganoDry')); assert(!v.rows.some(a => a.ingredient === 'parsleyDry')); });
test('土豆固定干迷迭香、牛肉固定鲜枝', () => { const p = buildPlan(db, state(['rosemary-potato', 'rosemary-beef'])); assert(row(p, 'rosemaryDry')); assert(row(p, 'rosemaryFresh')); });
test('熟虾/生虾、整玉米/玉米粒不会错误合并', () => { const p = buildPlan(db, state(['summer-roll', 'lemon-shrimp', 'miso-corn', 'lime-corn'])); for (const id of ['shrimpCooked', 'shrimp', 'corn', 'cornKernel'])
    assert(row(p, id)); });
test('批次保底蒸贝水：半份仍150ml，汤量随份量缩小', () => { const p = buildPlan(db, state(['clams-tofu'], { 'clams-tofu': .5 })); assert.equal(row(p, 'water').qty, 300); assert.equal(row(p, 'water').uses.find(x => x.scaling === 'batch').qty, 150); assert.equal(row(p, 'clams').qty, 225); });
test('三份花蛤按三批、保底水与汤总量一致', () => { const p = buildPlan(db, state(['clams-tofu'], { 'clams-tofu': 3 })); assert.equal(p.views[0].batches, 3); assert.equal(row(p, 'water').qty, 1350); });
test('半份焖鱼不会把锅底水减为20ml', () => { const p = buildPlan(db, state(['ginger-fish'], { 'ginger-fish': .5 })); assert.equal(row(p, 'water').qty, 40); });
test('米纸浸泡水按批、不是500ml全部算饮料', () => { const p = buildPlan(db, state(['summer-roll'], { 'summer-roll': .5 })); assert.equal(row(p, 'water').qty, 407.5); assert(row(p, 'water').uses.some(u => u.form.includes('不全部吃下'))); });
test('柠檬汁和皮屑同果复用取最大，不相加', () => { const p = buildPlan(db, state(['lemon-shrimp', 'lemon-asparagus'])); const x = p.procurement.find(x => x.id === 'lemon'); assert(x); assert.equal(x.qty, 1); assert.equal(x.method, 'max'); });
test('柠檬皮需求超过汁时按皮算采购', () => { const d = clone(db); d.recipes.find(r => r.id === 'lemon-shrimp').ingredients.find(a => a.ingredient === 'lemonZest').qty = 5; const p = buildPlan(d, state(['lemon-shrimp'])); const x = p.procurement.find(x => x.id === 'lemon'); assert.equal(x.qty, Math.ceil(5 / d.ingredients.lemonZest.purchase.yield)); });
test('蛋液+整蛋采购必须相加，不能套柠檬max算法', () => { const p = buildPlan(db, state(['okonomiyaki', 'lemon-pancakes', 'shakshuka'])); assert.equal(p.procurement.find(x => x.id === 'egg').qty, 4); });
test('熟米饭原料计算与采购生米换算分开', () => { const p = buildPlan(db, state(['soy-rice', 'onigiri-chazuke'])); assert.equal(row(p, 'rice').qty, 440); assert.equal(p.procurement.find(x => x.id === 'dryRice').qty, 180); });
test('菜单不会擅自去掉已知两瓶调料', () => { const p = buildPlan(db, state(['pepper-chicken', 'cumin-beef-wrap'])); assert(row(p, 'pepperMix').pantryHint); assert(row(p, 'cuminMix').pantryHint); assert.equal(row(p, 'pepperMix').qty, 3); });
test('四分之一份茶匙保留非零小数', () => { assert.notEqual(formatQty(.015625, 'tsp'), '0 茶匙'); assert.equal(formatQty(.125, 'tsp'), '⅛ 茶匙'); assert.equal(formatQty(1.5, 'tsp'), '1½ 茶匙'); });
test('食材勾选在相关需求变化时失效', () => { const s = state(['rosemary-beef']), p = buildPlan(db, s), x = row(p, 'beef'); setChecked(s, 'shop', 'beef', x.signature, true); assert(isChecked(s, 'shop', 'beef', x.signature)); s.portions['rosemary-beef'] = .5; assert(!isChecked(s, 'shop', 'beef', row(buildPlan(db, s), 'beef').signature)); });
test('步骤勾选在份量/配方步骤/修订改变时失效', () => { const s = state(['rosemary-beef']), v = recipeView(db, 'rosemary-beef', s); setChecked(s, 'step', 'rosemary-beef:0', v.signature, true); assert(isChecked(s, 'step', 'rosemary-beef:0', v.signature)); const d = clone(db); d.recipes.find(r => r.id === 'rosemary-beef').steps[0] += ' 测试修订'; assert(!isChecked(s, 'step', 'rosemary-beef:0', recipeView(d, 'rosemary-beef', s).signature)); });
test('取消勾选会删键', () => { const s = defaultState(); setChecked(s, 'shop', 'x', 'a', true); setChecked(s, 'shop', 'x', 'a', false); assert.equal(Object.keys(s.checked).length, 0); });
test('推荐顺序与手动顺序均稳定', () => { const s = state(['mint-pineapple', 'rosemary-beef', 'basil-toast']); assert.equal(buildPlan(db, s).views[0].id, 'basil-toast'); s.order = ['rosemary-beef', 'basil-toast', 'mint-pineapple']; assert.equal(buildPlan(db, s).views[0].id, 'rosemary-beef'); });
test('重复味型和过多主材有说明，不作为硬禁止', () => { const p = buildPlan(db, state(['rosemary-beef', 'rosemary-potato', 'camembert-dip', 'chimi-beef'])); assert(p.issues.some(x => x.kind === 'profile')); assert(p.issues.some(x => x.kind === 'main')); assert.equal(p.views.length, 4); });
test('超操作量、浓味堆叠和缺清爽都会提示', () => { const p = buildPlan(db, state(['camembert-dip', 'halloumi', 'bean-quesadilla', 'pita-pizza', 'smash-taco', 'rosemary-potato', 'kimchi-cheese-rice', 'mustard-chicken'])); for (const k of ['workload', 'rich', 'light', 'count'])
    assert(p.issues.some(i => i.kind === k), k); });
test('冷冻是设备前提，不触发食谱替换', () => { const s = state(['sweetpotato-dessert']); let p = buildPlan(db, s); assert(p.issues.some(i => i.kind === 'freezer')); assert(row(p, 'icecream')); assert(!row(p, 'yogurt')); s.hasFreezer = true; assert(!buildPlan(db, s).issues.some(i => i.kind === 'freezer')); });
test('补口建议不重复已选菜，不暗加到菜单', () => { const s = state(['smash-taco', 'smores']); const prior = clone(s), p = buildPlan(db, s); assert.equal(p.suggestions.length, 3); assert(p.suggestions.every(x => !s.selected.includes(x.id))); assert.deepEqual(s, prior); });
test('每套预设引用有效且不修改原输入', () => { for (const p of db.presets) {
    const s = defaultState(), out = applyPreset(db, s, p.id);
    assert.equal(s.selected.length, 0);
    assert.deepEqual(out.selected, Object.keys(p.selected));
    assert(buildPlan(db, out).shopping.length > 0);
} });
test('v2备份往返保持选菜、顺序、份量、笔记、历史与勾选', () => { let s = applyPreset(db, defaultState(), 'play-date'); s.notes['smash-taco'] = '不糊弄，压薄一点'; s.history = [{ at: '2026-09-16', name: '第一晚', ids: ['smash-taco'] }]; const backup = makeBackup(db, s); assert.deepEqual(importBackup(backup, db).state, sanitizeState(s, db)); });
test('v1菜单迁移固定配方，保留份量，报告退役不暗替换', () => { const v1 = { app: 'campfire-kitchen', backupVersion: 1, state: { people: 2, selected: ['rosemary-beef', 'miso-rice', 'miso-eggplant'], configs: { 'rosemary-beef': { portion: .5, choices: { herb: 'dry' } }, 'miso-rice': { portion: .75 } }, notes: { 'rosemary-beef': '旧笔记' }, checked: { foo: 'a' }, stepChecks: { bar: 'b' }, herbMode: 'dry' } }; const { state: s, warnings } = importBackup(v1, db); assert.deepEqual(s.selected, ['rosemary-beef', 'miso-eggplant']); assert.equal(s.portions['rosemary-beef'], .5); assert.equal(s.notes['rosemary-beef'], '旧笔记'); assert.equal(Object.keys(s.checked).length, 0); assert(!('herbMode' in s)); assert(!s.selected.includes('onigiri-chazuke')); assert(warnings.length >= 3); });
test('恶意或缺失旧选择对象不会导致原型污染', () => { const x = JSON.parse('{"people":100,"selected":["constructor","smash-taco","smash-taco"],"portions":{"__proto__":2,"smash-taco":-8},"checked":{"__proto__":"x"}}'); const s = sanitizeState(x, db); assert.equal(s.people, 16); assert.deepEqual(s.selected, ['smash-taco']); assert.equal(s.portions['smash-taco'], .25); assert.equal({}.polluted, undefined); });
test('非法备份不被当作菜单', () => { assert.throws(() => importBackup({ state: {} }, db)); assert.throws(() => importBackup({ app: 'campfire-kitchen', backupVersion: 999, state: {} }, db)); assert.doesNotThrow(() => importBackup({ app: 'campfire-kitchen', backupVersion: 1, state: { selected: 7 } }, db)); });
test('Markdown包含本菜份量、全步骤、形态和安全，不留模板变量', () => { const s = applyPreset(db, defaultState(), 'play-date'), md = makeMarkdown(db, s); assert(md.includes('压烤牛肉塔可')); assert(md.includes('71℃')); assert(md.includes('采购折算')); assert(md.includes('浸泡水')); assert(!md.includes('{{')); assert(md.includes('来源') || md.includes('依据')); });
test('CSV逐用途列出且防公式注入', () => { const d = clone(db); d.ingredients.beef.name = '=HYPERLINK("bad")'; const csv = makeCSV(d, state(['rosemary-beef'])); assert(csv.startsWith('\ufeff')); assert(csv.includes("'=HYPERLINK")); assert(csv.includes('拍裂')); });
test('HTML与URL输出转义，不接受javascript或嵌入凭据', () => { assert.equal(safeUrl('javascript:alert(1)'), ''); assert.equal(safeUrl('https://x:y@example.com'), ''); assert.equal(safeUrl('https://example.com/x'), 'https://example.com/x'); assert(!escapeHTML('<img onerror="alert(1)">').includes('<')); });
test('空菜单仍能导出和规划', () => { const s = defaultState(), p = buildPlan(db, s); assert.equal(p.views.length, 0); assert.equal(p.metrics.active, 0); assert.equal(p.suggestions.length, 0); assert(makeMarkdown(db, s).startsWith('#')); });
invalid('拒绝旧版鲜干菜谱库', d => { d.schemaVersion = 1; });
invalid('拒绝偷偷加回choices', d => { d.recipes[0].choices = []; });
invalid('拒绝optional材料选择', d => { d.recipes[0].ingredients[0].optional = true; });
invalid('拒绝重复菜谱ID', d => { d.recipes[1].id = d.recipes[0].id; });
invalid('拒绝重复原料行key', d => { d.recipes[0].ingredients[1].key = d.recipes[0].ingredients[0].key; });
invalid('拒绝不存在的原料', d => { d.recipes[0].ingredients[0].ingredient = 'notFound'; });
invalid('拒绝非有限数量', d => { d.recipes[0].ingredients[0].qty = Infinity; });
invalid('拒绝负数数量', d => { d.recipes[0].ingredients[0].qty = -2; });
invalid('拒绝未知单位', d => { d.ingredients.beef.unit = '随意'; });
invalid('拒绝无效模板引用', d => { d.recipes[0].steps.push('{{absent}}'); });
invalid('拒绝错误采购产率', d => { d.ingredients.egg.purchase.yield = 0; });
invalid('拒绝跨原料采购规则矛盾', d => { d.ingredients.eggWhole.purchase.method = 'max'; });
invalid('拒绝无效外链', d => { d.sources.temp.url = 'javascript:evil()'; });
invalid('拒绝缺失研究来源', d => { d.recipes[0].sources = ['missing']; });
invalid('拒绝非法分批规则', d => { d.recipes[0].ingredients[0].scaling = 'anything'; });
invalid('拒绝主动操作超过总时间', d => { d.recipes[0].activeMinutes = 999; });
invalid('拒绝原型名原料ID', d => { d.ingredients.constructor = { ...d.ingredients.beef }; });
invalid('拒绝空菜单库', d => { d.recipes = []; });
invalid('拒绝过长用户可渲染文字', d => { d.recipes[0].steps[0] = 'x'.repeat(6000); });
test('同一口感家族合并计数，不把每个修辞都算一种', () => { const p = buildPlan(db, state(['rosemary-beef', 'chimi-beef', 'mustard-chicken'])); assert.equal(p.metrics.textures, 1); assert(p.issues.some(x => x.kind === 'texture')); assert.equal(p.views.length, 3); });
test('完整v2备份的无效数据库不能绕过导入校验', () => { const b = makeBackup(db, defaultState()); b.database = clone(db); b.database.recipes[0].ingredients[0].qty = -1; assert.throws(() => importBackup(b, db), /菜谱库无效/); });
invalid('缺少口感分类不能伪造全新体验', d => { delete d.recipes[0].textureFamily; });
