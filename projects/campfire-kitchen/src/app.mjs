import { makeInventoryIndex, sanitizeInventory, inventoryCandidates, matchInventory, searchEntries } from './core/pantry.mjs';
import { suggestMeals } from './core/recommendations.mjs';
import { readJSONStorage, writeJSONStorage } from './core/storage.mjs';
import { E, button, metric, fraction, recipeCards } from './ui/components.mjs';
import { browseView } from './ui/browse.mjs';
import { pantryView } from './ui/pantry.mjs';
import { menuView, prepView } from './ui/planning.mjs';
import { settingsView } from './ui/settings.mjs';
import { renderRecipeDialog } from './ui/recipe.mjs';
import { APP_ID, LIMITS, validateDatabase, defaultState, sanitizeState, recipeView, selectedViews, buildPlan, applyPreset, makeBackup, importBackup, makeMarkdown, makeCSV, formatQty, escapeHTML, safeUrl, isChecked, setChecked } from './engine.mjs';
/** Offline UI. All user/imported text is escaped; catalog never supplies executable markup. */
const BUILTIN = JSON.parse(document.getElementById('recipe-data').textContent);
const STORE = 'campfire-kitchen-state-v2', LIB = 'campfire-kitchen-library-v2';
const root = document.getElementById('app'), dialog = document.getElementById('recipe-dialog');
const PHOTOS = JSON.parse(document.getElementById('photo-data').textContent);
const EQUIPMENT = JSON.parse(document.getElementById('equipment-data').textContent);
const INVENTORY_STORE = 'campfire-kitchen-pantry-v1';
let index, inventory, pantryQuery = '', matchFilter = 'ready', inventoryRaw = '', dialogTrigger = '';
const detailState = new Map();
let db = BUILTIN, state = defaultState(), tab = 'browse', search = '', category = '全部', experience = '全部', freshIdeas = false, onlyMissing = false, dialogId = null, presetCycle = 0, storageOK = true, banner = '', failedRaw = '', timerTick = null, lastRenderedTab = null;
const validation = validateDatabase(BUILTIN);
if (!validation.ok)
    throw new Error('内置菜谱校验失败：' + validation.errors.join('；'));
function readStore(key) { try {
    return localStorage.getItem(key);
}
catch {
    storageOK = false;
    return null;
} }
function writeStore(key, value) { try {
    localStorage.setItem(key, value);
    return true;
}
catch {
    storageOK = false;
    return false;
} }
try {
    const lib = readStore(LIB);
    if (lib) {
        const candidate = JSON.parse(lib), v = validateDatabase(candidate);
        if (v.ok)
            db = candidate;
        else
            banner = '保存的自定义库没有通过v2校验，已暂用内置库。原数据仍在本机；可导出救援数据。';
    }
}
catch {
    banner = '保存的自定义菜谱库无法读取，已暂用内置库；原数据未删除。';
}
try {
    const raw = readStore(STORE);
    if (raw) {
        failedRaw = raw;
        state = sanitizeState(JSON.parse(raw), db);
        failedRaw = '';
    }
}
catch {
    banner = '保存的菜单JSON损坏，未删除原值；点「救援原数据」保存后再重选。';
}
function rebuildIndex() {
    index = makeInventoryIndex(db, EQUIPMENT);
    inventory = sanitizeInventory(inventory, index);
}
rebuildIndex();
try {
    const saved = readJSONStorage(localStorage, INVENTORY_STORE);
    inventory = sanitizeInventory(saved.value, index);
    if (!saved.ok) {
        inventoryRaw = saved.raw || '';
        if (!saved.raw) storageOK = false;
        banner = '库存数据暂时无法读取；菜单不受影响。原值保留，可导出救援数据。';
    }
} catch { storageOK = false; }
function persistInventory() {
    if (inventoryRaw && !writeStore(INVENTORY_STORE + '-recovery', inventoryRaw)) return;
    try { if (!writeJSONStorage(localStorage, INVENTORY_STORE, inventory)) storageOK = false; }
    catch { storageOK = false; }
}
function filteredRecipes() {
    return searchEntries(index, {categories:category==='全部'?[]:[category],query:search,experience,
        exclude:freshIdeas ? state.history.slice(-3).flatMap(h=>h.ids):[]});
}
function context() {
    const matches = tab === 'pantry' ? matchInventory(index,inventory,{hasFreezer:state.hasFreezer}) : [];
    return {db,state,photos:PHOTOS,index,inventory,search,category,experience,freshIdeas,onlyMissing,
        pantryQuery,matchFilter,matches,meals:tab==='pantry'?suggestMeals(db,matches,state):[],
        recipes:filteredRecipes(),renderPeople,portionControl,findRecipe,sourceLinks};
}
function renderCards() { return recipeCards(filteredRecipes(),context()); }
function renderDialog() { renderRecipeDialog({...context(),dialogId,dialog,toggleButton,updateTimer}); }
function elementSelector(el) {
    if (!el || el===document.body) return '';
    if (el.id) return '#'+CSS.escape(el.id);
    const names=['data-action','data-change','data-id','data-key','data-kind','data-value','data-tab','data-scope','data-mode','data-group','data-delta'];
    const selectors=names.filter(n=>el.hasAttribute(n)).map(n=>`[${n}="${CSS.escape(el.getAttribute(n))}"]`).join('');
    return selectors ? el.tagName.toLowerCase()+selectors+[...el.classList].map(c=>'.'+CSS.escape(c)).join('') : '';
}
function render() {
    const sameTab=lastRenderedTab===tab, scroll=sameTab?window.scrollY:0;
    const focused=root.contains(document.activeElement)?elementSelector(document.activeElement):'';
    const selection=document.activeElement?.selectionStart;
    const innerScroll=root.querySelector('.inventory-scroll')?.scrollTop||0;
    root.querySelectorAll('details[data-keep]').forEach(d=>detailState.set(d.dataset.keep,d.open));
    lastRenderedTab=tab;
    const ctx=context();
    const page=tab==='browse'?browseView(ctx):tab==='pantry'?pantryView(ctx):tab==='menu'?menuView(ctx):tab==='prep'?prepView(ctx):settingsView(ctx);
    root.innerHTML=`<header class="site-header"><div class="topbar"><a class="brand" href="#browse" data-action="tab" data-tab="browse"><span class="brand-icon" aria-hidden="true">火</span><span>火边<small>露营风味厨房</small></span></a><nav class="tabs" aria-label="主导航">${[['browse','看菜谱'],['pantry','我有这些'],['menu','这顿菜单']].map(([key,label])=>button(label+(key==='menu'&&state.selected.length?` <b>${state.selected.length}</b>`:''),'tab',`data-tab="${key}" ${key===tab||key==='menu'&&tab==='prep'?'aria-current="page"':''}`,key===tab||key==='menu'&&tab==='prep'?'active':'')).join('')}</nav><span class="offline-dot">离线可用</span></div></header>
    ${banner?`<div class="banner" role="status">${E(banner)} ${button('救援原数据','rescue','','text-btn')}${button('关闭提示','dismiss-banner','','text-btn')}</div>`:''}
    ${!storageOK?'<div class="banner warn" role="status">本地保存不可用。离开前请导出完整备份；不影响当前操作。</div>':''}
    <main id="main" tabindex="-1">${tab==='menu'||tab==='prep'?`<nav class="workflow-nav" aria-label="这顿菜单与备料">${button('① 安排这顿','tab','data-tab="menu" '+(tab==='menu'?'aria-current="page"':''),tab==='menu'?'active':'')}${button('② 备料与分装','tab','data-tab="prep" '+(tab==='prep'?'aria-current="page"':''),tab==='prep'?'active':'')}</nav>`:''}${page}</main>
    <footer><span>火边 v${E(BUILTIN.version)} · 无联网请求，不上传选择</span><div>${button('资料与管理','tab','data-tab="review"','text-btn')}${button('导出完整备份','export-backup','','text-btn')}</div></footer>
    <div class="bottom-dock"><div><b>${state.selected.length} 道</b><span> / ${state.people} 人</span></div>${tab==='pantry'?button(`看可做的菜 · ${ctx.matches.filter(m=>m.ready).length}`,'jump-results','','btn primary'):button(tab==='prep'?'回到这顿':'看这顿与备料','tab',`data-tab="${tab==='menu'?'prep':'menu'}"`,'btn primary')}${state.selected.length?button('清空菜单','clear','','text-btn'):''}</div>`;
    root.querySelectorAll('details[data-keep]').forEach(d=>{if(detailState.has(d.dataset.keep)&&!(tab==='pantry'&&pantryQuery&&d.classList.contains('inventory-group')))d.open=detailState.get(d.dataset.keep);});
    const panel=root.querySelector('.inventory-scroll'); if(panel)panel.scrollTop=innerScroll;
    if (sameTab&&focused) {
        const target=root.querySelector(focused);
        target?.focus({preventScroll:true});
        if (target&&Number.isInteger(selection)&&typeof target.setSelectionRange==='function') {try {target.setSelectionRange(selection,selection);}catch{}}
    }
    if (dialogId&&dialog.open) renderDialog();
    updateTimer();
    requestAnimationFrame(()=>window.scrollTo(0,scroll));
}
function applyMeal(id) {
    const meals=suggestMeals(db,matchInventory(index,inventory,{hasFreezer:state.hasFreezer}),state);
    const meal=meals.find(m=>m.id===id);
    if (!meal) return toast('库存或分类已变化，请重新选择可做的组合。');
    if (state.selected.length&&!confirm('用这组可做菜替换当前菜单？每道设为1份，笔记保留；原菜单建议先导出备份。')) return;
    state.selected=meal.recipes.map(r=>r.id); state.order=[...state.selected];
    state.portions=Object.fromEntries(state.selected.map(id=>[id,1]));
    state.checked={};state.steps={};state.menuName=meal.title;
    tab='menu'; location.hash='menu'; save('已加入组合，请到备料页核对所有菜的合计用量。');
}

function persist() { persistInventory(); if (failedRaw && !writeStore(STORE + '-recovery', failedRaw))
    return; writeStore(STORE, JSON.stringify(state)); }
function toast(message) { const el = document.getElementById('toast'); el.textContent = message; el.hidden = false; clearTimeout(toast.timeout); toast.timeout = setTimeout(() => { el.hidden = true; }, 4200); }
function save(message) { persist(); render(); if (message)
    toast(message); }
function toggleButton(id, compact = false) { const yes = state.selected.includes(id); return button(yes ? '✓ 已加入' : '+ 加入这顿', 'toggle', `data-id="${E(id)}" aria-pressed="${yes}"`, yes ? 'btn selected' : 'btn' + (compact ? ' small' : '')); }
function portionControl(id, scope = 'card') { const current = state.portions[id] ?? 1, values = [.25, .5, .75, 1, 1.5, 2, 3, 4]; if (!values.includes(current))
    values.push(current); return `<label class="portion">本菜份量 <select aria-label="${E(db.recipes.find(r => r.id === id)?.title)}份量" data-change="portion" data-id="${E(id)}" data-scope="${scope}">${values.sort((a, b) => a - b).map(n => `<option value="${n}" ${n === current ? 'selected' : ''}>${fraction(n)}</option>`).join('')}</select></label>`; }
function sourceLinks(ids) { return ids.map(id => { const s = db.sources[id]; return s ? `<a href="${E(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${E(s.title)} ↗</a>` : ''; }).join(''); }
function findRecipe(id) { return db.recipes.find(r => r.id === id); }
function renderPeople() { return `<div class="people-control"><span>用餐人数</span>${button('−', 'people', 'data-delta="-1" aria-label="减少人数"', 'round-btn')}<strong aria-live="polite">${state.people}</strong>${button('+', 'people', 'data-delta="1" aria-label="增加人数"', 'round-btn')}</div>`; }
function openRecipe(id) { if (!findRecipe(id))
    return; if(!dialog.open)dialogTrigger=elementSelector(document.activeElement); const switched = dialogId !== id; dialogId = id; renderDialog(); if (!dialog.open)
    dialog.showModal(); if (switched)
    dialog.querySelector('.dialog-body').scrollTop = 0; }
function closeDialog() { dialog.close(); dialogId = null; }
function doToggle(id) { if (!findRecipe(id))
    return; if (state.selected.includes(id)) {
    state.selected = state.selected.filter(x => x !== id);
    state.order = state.order.filter(x => x !== id);
}
else {
    if (state.selected.length >= 50) {
        toast('一桌最多选择50道。');
        return;
    }
    state.selected.push(id);
    if (state.order.length)
        state.order.push(id);
} save(); }
function download(name, contents, type = 'application/json;charset=utf-8') { const blob = new Blob([contents], { type }), url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000); }
function dateName() { return new Date().toISOString().slice(0, 10); }
function switchTab(name) { if (!['browse', 'pantry', 'menu', 'prep', 'review'].includes(name))
    return; tab = name; if(location.hash!=='#'+name) { try { history.replaceState(null,'','#'+name); } catch { /* Opaque preview origins may deny history writes. */ } } render(); window.scrollTo({ top: 0, behavior: 'instant' }); }
function usePreset(id) { if (state.selected.length && !confirm('用这套定稿菜单替换当前选菜？笔记保留；原菜单建议先导出备份。'))
    return; state = applyPreset(db, state, id); tab = 'menu'; save('已排好这一桌，可调每道份量。'); window.scrollTo(0, 0); }
function updateTimer() { const el = document.getElementById('timer-readout'); if (!el)
    return; if (!state.timer) {
    el.textContent = '未计时';
    return;
} const sec = Math.max(0, Math.ceil((state.timer.endsAt - Date.now()) / 1000)); el.textContent = sec ? `${state.timer.label} · ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}` : '时间到了：检查食物，不代表已经熟透。'; el.classList.toggle('timer-done', sec === 0); }
document.addEventListener('click', event => {
    const b = event.target.closest('[data-action]');
    if (!b)
        return;
    const a = b.dataset.action, id = b.dataset.id;
    event.preventDefault();
    if (a === 'tab')
        switchTab(b.dataset.tab);
    else if (a === 'detail')
        openRecipe(id);
    else if (a === 'close-dialog')
        closeDialog();
    else if (a === 'toggle')
        doToggle(id);
    else if (a === 'category') {
        category = b.dataset.value || '全部';
        render();
    }
    else if (a === 'scope') {
        const value=b.dataset.value;
        inventory.categories=value?(inventory.categories.includes(value)?inventory.categories.filter(c=>c!==value):[...inventory.categories,value]):[];
        persistInventory();render();
    }
    else if (a === 'match-filter') {
        if (['ready','ingredients','equipment','all'].includes(b.dataset.value)) matchFilter=b.dataset.value;
        render();
    }
    else if (a === 'inventory-group') {
        const kind=b.dataset.kind;
        if (!['ingredients','tools'].includes(kind)) return;
        const ids=inventoryCandidates(index,inventory.categories,pantryQuery)[kind].filter(i=>i.group===b.dataset.group).map(i=>i.id);
        const owned=new Set(inventory[kind]); ids.forEach(id=>b.dataset.mode==='select'?owned.add(id):owned.delete(id));
        inventory[kind]=[...owned];persistInventory();render();
    }
    else if (a === 'clear-inventory') {
        if (confirm('清空食材和工具库存？菜谱分类、这顿菜单与笔记保留。')) {
            inventory.ingredients=[];inventory.tools=[];persistInventory();render();
        }
    }
    else if (a === 'jump-results') {
        const target=document.getElementById('inventory-results');
        target?.scrollIntoView({block:'start',behavior:'instant'});target?.focus({preventScroll:true});
    }
    else if (a === 'apply-meal') applyMeal(id);
    else if (a === 'people') {
        state.people = Math.max(1, Math.min(LIMITS.people, state.people + Number(b.dataset.delta)));
        save();
    }
    else if (a === 'preset')
        usePreset(id);
    else if (a === 'inspire') {
        const p = db.presets[presetCycle++ % db.presets.length];
        usePreset(p.id);
    }
    else if (a === 'clear') {
        if (state.selected.length && confirm('清空本次选菜与完成勾选？个人菜谱笔记保留。')) {
            state.selected = [];
            state.order = [];
            state.checked = {};
            state.steps = {};
            save('已清空本次菜单。');
        }
    }
    else if (a === 'sort') {
        state.order = [];
        save();
    }
    else if (a === 'move') {
        const ids = selectedViews(db, state).map(r => r.id), j = ids.indexOf(id), next = j + Number(b.dataset.delta);
        if (j >= 0 && next >= 0 && next < ids.length) {
            [ids[j], ids[next]] = [ids[next], ids[j]];
            state.order = ids;
            save();
        }
    }
    else if (a === 'record') {
        if (!state.selected.length)
            return;
        if (!confirm('记录当前菜单为本次已做过？这不会删除选菜。'))
            return;
        state.history.push({ at: new Date().toISOString(), name: state.menuName, ids: [...state.selected] });
        state.history = state.history.slice(-30);
        save('已记录；下次可筛掉最近三次做过的菜。');
    }
    else if (a === 'export-backup')
        download(`火边完整备份-${dateName()}.json`, JSON.stringify({...makeBackup(db, state),inventory}, null, 2));
    else if (a === 'export-library')
        download('火边定稿菜谱库.json', JSON.stringify(db, null, 2));
    else if (a === 'export-md')
        download(`火边行动单-${dateName()}.md`, makeMarkdown(db, state), 'text/markdown;charset=utf-8');
    else if (a === 'export-csv')
        download(`火边备料-${dateName()}.csv`, makeCSV(db, state), 'text/csv;charset=utf-8');
    else if (a === 'print') {
        const target = document.getElementById('print-container');
        target.innerHTML = `<h1>${E(state.menuName)}</h1><pre>${E(makeMarkdown(db, state))}</pre>`;
        window.print();
    }
    else if (a === 'import-backup')
        document.getElementById('backup-import').click();
    else if (a === 'import-library')
        document.getElementById('library-import').click();
    else if (a === 'restore-library') {
        if (confirm('恢复内置定稿库？自定义库会移除，仍存在的选菜与笔记保留；请先导出自定义库。')) {
            db = BUILTIN;
            rebuildIndex();
            state = sanitizeState(state, db);
            state.checked = {};
            state.steps = {};
            try {
                localStorage.removeItem(LIB);
            }
            catch {
                storageOK = false;
            }
            save('已恢复内置定稿库。');
        }
    }
    else if (a === 'timer') {
        state.timer = { endsAt: Date.now() + Number(b.dataset.minutes) * 60000, label: findRecipe(id)?.title ?? '检查食物' };
        persist();
        updateTimer();
    }
    else if (a === 'stop-timer') {
        state.timer = null;
        persist();
        updateTimer();
    }
    else if (a === 'rescue') {
        download('火边本机数据救援.json', JSON.stringify({ stateRaw: failedRaw || readStore(STORE + '-recovery') || readStore(STORE), libraryRaw: readStore(LIB),inventoryRaw: inventoryRaw || readStore(INVENTORY_STORE + '-recovery') || readStore(INVENTORY_STORE) }, null, 2));
    }
    else if (a === 'dismiss-banner') {
        banner = '';
        render();
    }
});
document.addEventListener('input', event => {
    const t = event.target;
    if (t.id === 'recipe-search') {
        search = t.value;
        document.getElementById('catalog-list').innerHTML = renderCards();
        document.getElementById('recipe-count').textContent = `${filteredRecipes().length} / ${db.recipes.length}道`;
    }
    else if (t.id === 'pantry-search') {
        pantryQuery=t.value;render();
    }
    else if (t.id === 'menu-name') {
        state.menuName = t.value.slice(0, 100);
        persist();
    }
    else if (t.dataset.change === 'note') {
        state.notes[t.dataset.id] = t.value.slice(0, 3000);
        persist();
    }
});
document.addEventListener('change', event => {
    const t = event.target, a = t.dataset.change, id = t.dataset.id;
    if (!a)
        return;
    if (a === 'inventory') {
        const kind=t.dataset.kind;
        if (!['ingredients','tools'].includes(kind)) return;
        const allowed=kind==='ingredients'?index.usedIngredients:index.usedTools;
        if (!allowed.has(id)) return;
        const owned=new Set(inventory[kind]);t.checked?owned.add(id):owned.delete(id);
        inventory[kind]=[...owned];persistInventory();render();
    }
    else if (a === 'portion') {
        const n = Number(t.value);
        if (Number.isFinite(n) && n >= .25 && n <= 4) {
            state.portions[id] = n;
            save();
        }
    }
    else if (a === 'experience') {
        experience = t.value;
        render();
    }
    else if (a === 'fresh-ideas') {
        freshIdeas = t.checked;
        render();
    }
    else if (a === 'freezer') {
        state.hasFreezer = t.checked;
        save();
    }
    else if (a === 'only-missing') {
        onlyMissing = t.checked;
        render();
    }
    else if (a === 'check') {
        setChecked(state, t.dataset.kind, t.dataset.key, t.dataset.sig, t.checked);
        persist();
        if (onlyMissing && t.dataset.kind === 'shop')
            render();
        else
            t.closest('.task')?.classList.toggle('done', t.checked);
    }
    else if (a === 'step') {
        setChecked(state, 'step', id + ':' + t.dataset.key, t.dataset.sig, t.checked);
        persist();
        renderDialog();
    }
});
async function readJSONFile(input) { const file = input.files?.[0]; if (!file)
    return null; if (file.size > LIMITS.fileBytes)
    throw new Error('文件超过5MB上限。'); const value = JSON.parse(await file.text()); return value; }
document.getElementById('backup-import').addEventListener('change', async (event) => { const input = event.target; try {
    const value = await readJSONFile(input);
    if (!value)
        return;
    const result = importBackup(value, db);
    if (!confirm(value.backupVersion === 1 ? '迁移旧菜单到本版定稿配方？旧鲜干库不沿用，建议先导出当前备份。' : '导入并替换菜谱库和当前菜单？建议先导出当前完整备份。'))
        return;
    db = result.database;
    state = result.state;
    index=makeInventoryIndex(db,EQUIPMENT);
    inventory=sanitizeInventory(value.inventory??inventory,index);
    if (value.backupVersion === 2 && value.database)
        writeStore(LIB, JSON.stringify(db));
    banner = result.warnings.join(' ');
    tab = 'menu';
    save(result.warnings.length ? '已迁移，请查看上方变更提示。' : '菜单备份已恢复。');
}
catch (e) {
    toast('导入失败：' + e.message);
}
finally {
    input.value = '';
} });
document.getElementById('library-import').addEventListener('change', async (event) => { const input = event.target; try {
    const value = await readJSONFile(input);
    if (!value)
        return;
    const result = validateDatabase(value);
    if (!result.ok)
        throw new Error(result.errors.slice(0, 5).join('；'));
    if (!confirm(`导入${value.recipes.length}道定稿菜谱并替换当前库？完成勾选将清空，现存ID的菜单和笔记保留。`))
        return;
    db = value;
    rebuildIndex();
    state = sanitizeState(state, db);
    state.checked = {};
    state.steps = {};
    writeStore(LIB, JSON.stringify(db));
    tab = 'review';
    save('菜谱库已校验并导入。');
}
catch (e) {
    toast('菜谱库未导入：' + e.message);
}
finally {
    input.value = '';
} });
dialog.addEventListener('close', () => { dialogId = null; if(dialogTrigger)root.querySelector(dialogTrigger)?.focus({preventScroll:true}); });
dialog.addEventListener('click', e => { if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
        closeDialog();
} });
document.addEventListener('visibilitychange', updateTimer);
timerTick = setInterval(updateTimer, 1000);
window.addEventListener('pagehide', () => { persist(); clearInterval(timerTick); });
window.addEventListener('pageshow', () => { clearInterval(timerTick); timerTick = setInterval(updateTimer, 1000); updateTimer(); });
const initialTab=location.hash.slice(1);
if (['browse','pantry','menu','prep','review'].includes(initialTab)) tab=initialTab;
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(next!==tab)switchTab(next);});
render();
