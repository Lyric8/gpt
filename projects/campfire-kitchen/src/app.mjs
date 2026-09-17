import { APP_ID, LIMITS, validateDatabase, defaultState, sanitizeState, recipeView, selectedViews, buildPlan, applyPreset, makeBackup, importBackup, makeMarkdown, makeCSV, formatQty, escapeHTML, safeUrl, isChecked, setChecked } from './engine.mjs';
/** Offline UI. All user/imported text is escaped; catalog never supplies executable markup. */
const BUILTIN = JSON.parse(document.getElementById('recipe-data').textContent);
const STORE = 'campfire-kitchen-state-v2', LIB = 'campfire-kitchen-library-v2';
const root = document.getElementById('app'), dialog = document.getElementById('recipe-dialog');
const E = escapeHTML;
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
function persist() { if (failedRaw && !writeStore(STORE + '-recovery', failedRaw))
    return; writeStore(STORE, JSON.stringify(state)); }
function toast(message) { const el = document.getElementById('toast'); el.textContent = message; el.hidden = false; clearTimeout(toast.timeout); toast.timeout = setTimeout(() => { el.hidden = true; }, 4200); }
function save(message) { persist(); render(); if (message)
    toast(message); }
function metric(value, label) { return `<div class="metric"><strong>${E(value)}</strong><span>${E(label)}</span></div>`; }
function button(label, action, attrs = '', cls = 'btn') { return `<button class="${cls}" data-action="${action}" ${attrs}>${label}</button>`; }
function toggleButton(id, compact = false) { const yes = state.selected.includes(id); return button(yes ? '✓ 已加入' : '+ 加入这顿', 'toggle', `data-id="${E(id)}" aria-pressed="${yes}"`, yes ? 'btn selected' : 'btn' + (compact ? ' small' : '')); }
function fraction(n) { return ({ .25: '¼份', .5: '半份', .75: '¾份', 1: '1份', 1.5: '1½份', 2: '2份', 3: '3份', 4: '4份' })[n] ?? `${n}份`; }
function portionControl(id, scope = 'card') { const current = state.portions[id] ?? 1, values = [.25, .5, .75, 1, 1.5, 2, 3, 4]; if (!values.includes(current))
    values.push(current); return `<label class="portion">本菜份量 <select aria-label="${E(db.recipes.find(r => r.id === id)?.title)}份量" data-change="portion" data-id="${E(id)}" data-scope="${scope}">${values.sort((a, b) => a - b).map(n => `<option value="${n}" ${n === current ? 'selected' : ''}>${fraction(n)}</option>`).join('')}</select></label>`; }
function sourceLinks(ids) { return ids.map(id => { const s = db.sources[id]; return s ? `<a href="${E(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${E(s.title)} ↗</a>` : ''; }).join(''); }
function findRecipe(id) { return db.recipes.find(r => r.id === id); }
function render() {
    const scroll = lastRenderedTab === tab ? window.scrollY : 0;
    lastRenderedTab = tab;
    root.innerHTML = `<header class="topbar"><a class="brand" href="#" data-action="tab" data-tab="browse"><span class="brand-icon">火</span><span>火边<small>好好玩一顿 · v${E(db.version)}</small></span></a><div class="head-tools"><span class="offline-dot">离线可用</span>${button('备份', 'export-backup', '', 'btn ghost small')}</div></header>
 <nav class="tabs" aria-label="主导航">${[['browse', '挑菜与灵感'], ['menu', '这顿怎么吃'], ['prep', '备料与分装'], ['review', '配方与审查']].map(([key, label]) => `<button data-action="tab" data-tab="${key}" class="${key === tab ? 'active' : ''}" aria-current="${key === tab ? 'page' : 'false'}">${label}${key === 'menu' && state.selected.length ? `<b>${state.selected.length}</b>` : ''}</button>`).join('')}</nav>
 ${banner ? `<div class="banner">${E(banner)} ${button('救援原数据', 'rescue', '', 'text-btn')}${button('关闭提示', 'dismiss-banner', '', 'text-btn')}</div>` : ''}
 ${!storageOK ? '<div class="banner warn">浏览器不允许本地保存。程序仍可操作；离开前请导出JSON备份，不要依赖自动记忆。</div>' : ''}
 <main id="main">${tab === 'browse' ? renderBrowse() : tab === 'menu' ? renderMenu() : tab === 'prep' ? renderPrep() : renderReview()}</main>
 <footer><span>菜是定稿，菜单由你。净用量随人数与份量计算。</span><span>无联网请求 · 不上传选择与笔记</span></footer>
 <div class="bottom-dock"><div><b>${state.selected.length} 道</b><span> / ${state.people} 人</span></div>${button(tab === 'prep' ? '查看现场操作' : '看这顿与备料', 'tab', `data-tab="${tab === 'prep' ? 'menu' : 'prep'}"`, 'btn primary')}${button('清空', 'clear', '', 'text-btn')}</div>`;
    if (dialogId && dialog.open)
        renderDialog();
    updateTimer();
    requestAnimationFrame(() => { if (Math.abs(window.scrollY - scroll) > 60)
        window.scrollTo(0, scroll); });
}
function renderPeople() { return `<div class="people-control"><span>用餐人数</span>${button('−', 'people', 'data-delta="-1" aria-label="减少人数"', 'round-btn')}<strong aria-live="polite">${state.people}</strong>${button('+', 'people', 'data-delta="1" aria-label="增加人数"', 'round-btn')}</div>`; }
function filteredRecipes() { const history = new Set(state.history.slice(-3).flatMap(h => h.ids)), q = search.trim().toLowerCase(); return db.recipes.filter(r => (category === '全部' || r.category === category) && (experience === '全部' || r.interaction === experience) && (!freshIdeas || !history.has(r.id)) && (!q || [r.title, r.taste, r.texture, r.fun, r.technique, ...r.tags, ...r.ingredients.map(a => db.ingredients[a.ingredient].name)].join(' ').toLowerCase().includes(q))); }
function renderBrowse() {
    return `<section class="hero"><div><span class="eyebrow">不是再换一瓶烧烤粉</span><h1>有好吃的。<br>也有一起动手的。</h1><p>卷一只米纸、压一张脆塔可，或者给焦壳饭团浇热汤。<br class="desktop">每道的材料形态和做法已定好，选喜欢的就开做。</p></div><div class="hero-aside">${renderPeople()}<div class="hero-note"><b>${db.recipes.length} 道定稿操作卡</b><span>鲜叶、干料、成品酱各用在该用的地方。</span><span>多选自动合并原料，但保留各菜的形态与用量。</span></div></div></section>
 <section class="section"><div class="section-head"><div><span class="eyebrow">不用从${db.recipes.length}道里重新组一桌</span><h2>先挑一个心情</h2></div>${button('换一桌灵感', 'inspire', '', 'btn ghost')}</div><div class="preset-grid">${db.presets.map((p, j) => `<button class="preset-card" data-action="preset" data-id="${E(p.id)}"><span class="preset-no">0${j + 1}</span><strong>${E(p.name)}</strong><span>${E(p.note)}</span><small>${Object.keys(p.selected).length}道 · 点选前可确认替换</small></button>`).join('')}</div></section>
 <section class="section catalog"><div class="section-head"><h2>按想吃的、想玩的来</h2><span class="muted" id="recipe-count">${filteredRecipes().length} / ${db.recipes.length}道</span></div>
 <div class="search-row"><label class="search-box"><span>⌕</span><input id="recipe-search" type="search" placeholder="搜食物、味道、翻饼 / 手卷 / 脆壳…" value="${E(search)}" aria-label="搜索菜谱"></label><select id="experience-filter" aria-label="操作体验筛选" data-change="experience">${['全部', '动手', '轻操作', '保底'].map(x => `<option ${experience === x ? 'selected' : ''} value="${x}">${x === '全部' ? '全部体验' : x}</option>`).join('')}</select><label class="check-inline"><input type="checkbox" data-change="fresh-ideas" ${freshIdeas ? 'checked' : ''}>最近三次没做过</label></div>
 <div class="chips" role="group" aria-label="菜谱分类">${['全部', ...new Set(db.recipes.map(r => r.category))].map(c => `<button data-action="category" data-value="${E(c)}" class="chip ${category === c ? 'active' : ''}">${E(c)}</button>`).join('')}</div>
 <div class="recipe-grid" id="catalog-list">${renderCards()}</div></section>`;
}
function renderCards() { const recipes = filteredRecipes(); if (!recipes.length)
    return '<div class="empty">没有匹配的菜。换个关键词，或清除分类／最近没做过筛选。</div>'; return recipes.map(r => `<article class="recipe-card ${state.selected.includes(r.id) ? 'is-selected' : ''}" data-card="${E(r.id)}"><div class="card-meta"><span>${E(r.category)}</span><span>${r.activeMinutes}′ 主动操作</span></div><button class="card-title" data-action="detail" data-id="${E(r.id)}"><h3>${E(r.title)}</h3></button><p class="taste">${E(r.taste)}</p><div class="tag-row"><span>${E(r.texture)}</span><span>${E(r.moment)}</span>${r.needsFreezer ? '<span class="cold-tag">需要冷冻</span>' : ''}</div><p class="play"><b>玩什么</b>${E(r.fun)}</p><div class="card-bottom">${button('看操作卡 ↗', 'detail', `data-id="${E(r.id)}"`, 'text-btn')}${toggleButton(r.id, true)}</div></article>`).join(''); }
function issueBox(p) { return p.issues.length ? `<div class="issue-grid">${p.issues.map(x => `<div class="issue ${x.level}"><b>${E(x.title)}</b><p>${E(x.detail)}</p></div>`).join('')}</div>` : `<div class="issue good"><b>这桌暂未发现明显重复或超量操作信号</b><p>这是按菜数、味型、口感组、主材和操作量检查，不是对口味或食量的保证。</p></div>`; }
function renderMenu() {
    const p = buildPlan(db, state);
    return `<section class="section"><div class="section-head"><div><span class="eyebrow">一桌的节奏，比单道菜数量重要</span><h1 class="page-title">这顿怎么吃</h1></div>${renderPeople()}</div>
 <div class="menu-name"><label>菜单名字<input id="menu-name" maxlength="100" value="${E(state.menuName)}"></label><label class="check-inline"><input type="checkbox" data-change="freezer" ${state.hasFreezer ? 'checked' : ''}>本次有持续≤-18℃冷冻条件</label></div>
 ${!p.views.length ? emptyMenu() : `<div class="metrics">${metric(p.metrics.profiles, '种味型')}${metric(p.metrics.textures, '种口感')}${metric(p.metrics.active + '′', '现场主动操作估计')}${metric(p.metrics.home + '′', '家里预制逐项合计')}</div><p class="muted small-text">口感按共同结构合并统计，不是每个菜名算一种；分类不是实验评分。小份不会按比例缩短预热、翻面和收尾时间；家里任务可批量做，估计未自动抵扣。</p>${issueBox(p)}
 <div class="section-head compact"><h2>出餐顺序</h2><div class="actions">${button('恢复推荐顺序', 'sort', '', 'btn ghost small')}${button('备料清单', 'tab', 'data-tab="prep"', 'btn primary small')}</div></div>
 <p class="muted">先无火/开胃，再蔬菜、主菜、主食、甜品。下列${p.metrics.sequential}分钟是假设逐道制作的占用合计，不含生火、聊天与吃饭，不是离线精准排程。箭头可调整顺序。</p>
 <div class="menu-list">${p.views.map((r, j) => `<article class="menu-item" data-menu-item="${r.id}"><span class="order-no">${String(j + 1).padStart(2, '0')}</span><div class="menu-item-main"><h3>${E(r.title)}</h3><p>${E(r.taste)} · ${r.batches}批 · 约${r.totalEstimate}分钟</p><span class="muted">${E(r.texture)} / ${E(r.moment)}</span><div class="menu-item-tools">${portionControl(r.id, 'menu')}${button('开始做 / 操作卡', 'detail', `data-id="${r.id}"`, 'btn small')}</div></div><div class="reorder">${button('↑', 'move', `data-id="${r.id}" data-delta="-1" ${j === 0 ? 'disabled' : ''} aria-label="上移${E(r.title)}"`, 'round-btn')}${button('↓', 'move', `data-id="${r.id}" data-delta="1" ${j === p.views.length - 1 ? 'disabled' : ''} aria-label="下移${E(r.title)}"`, 'round-btn')}${button('移除', 'toggle', `data-id="${r.id}"`, 'text-btn')}</div></article>`).join('')}</div>
 <div class="suggestions"><h2>想换一口，而不是又多做三道</h2><p class="muted">按味型差别、主材、操作方式、采购新增项和最近记录挑选。下列是互补线索，不是保证“最佳”的黑箱评分。</p><div class="suggestion-grid">${p.suggestions.map(s => `<article><h3>${E(s.title)}</h3><p>${E(s.reasons.join(' · '))}</p><small>较当前清单新增约${s.extraIngredients}种原料（含家中可能已有的基础料）</small>${button('先看，不直接加', 'detail', `data-id="${s.id}"`, 'text-btn')}</article>`).join('')}</div></div>
 <div class="panel"><h3>这次做完以后</h3><p>记录这一桌，下一次「最近三次没做过」会避开它。不自动删除菜单。</p>${button('记录这次做过', 'record', '', 'btn')}${state.history.length ? `<span class="muted"> 已记录${state.history.length}次</span>` : ''}</div>`}</section>`;
}
function emptyMenu() { return `<div class="empty"><h2>先选想吃的，不用先买一箱调料。</h2><p>去挑一道菜或一套菜单。份量和备料会跟着算。</p>${button('去挑菜', 'tab', 'data-tab="browse"', 'btn primary')}</div>`; }
function prepCheck(kind, id, sig, label, extra = '') { const yes = isChecked(state, kind, id, sig); return `<label class="task ${yes ? 'done' : ''}"><input type="checkbox" data-change="check" data-kind="${kind}" data-key="${E(id)}" data-sig="${sig}" ${yes ? 'checked' : ''}><span>${label}${extra}</span></label>`; }
function renderPrep() {
    const p = buildPlan(db, state);
    if (!p.views.length)
        return `<section class="section"><h1 class="page-title">备料与分装</h1>${emptyMenu()}</section>`;
    const shopping = p.shopping.filter(x => !onlyMissing || !isChecked(state, 'shop', x.id, x.signature));
    return `<section class="section"><div class="section-head"><div><span class="eyebrow">原料合并，形态不合并</span><h1 class="page-title">${E(state.menuName)} · 备料</h1></div><div class="actions">${button('导出行动单 .md', 'export-md', '', 'btn primary')}${button('CSV', 'export-csv', '', 'btn ghost')}${button('打印', 'print', '', 'btn ghost')}</div></div>
 <div class="prep-summary">${state.people}人 · ${p.views.length}道 · ${p.shopping.length}种原料 <span>净用量不是必须购买的包装大小；你已提到有的两瓶料仅做提示，不自动从清单删除。</span></div>
 ${p.issues.some(x => x.level === 'danger') ? issueBox({ issues: p.issues.filter(x => x.level === 'danger') }) : ''}
 <details class="panel safety"><summary>冷链 / 熟度 / 过敏原（出发前看一次）</summary>${db.safety.map(x => `<p><b>${E(x.title)}</b> ${E(x.text)}</p>`).join('')}<p><b>本次涉及：</b>${E(p.allergens.join('、') || '数据未列出常见过敏原；仍查包装')}。商品配料标签优先。</p></details>
 ${p.procurement.length ? `<div class="panel purchase"><h2>先买多少：需要换算的几项</h2><p>下面是对净材料的采购折算，<b>不是再额外买一份</b>。柠檬同颗取汁取皮；鸡蛋各用途相加；熟饭换算生米。</p><div class="purchase-grid">${p.procurement.map(x => `<div><b>${E(x.name)}</b><strong>约 ${formatQty(x.qty, x.unit)}</strong><span>${x.components.map(c => E(c.name) + ' ' + formatQty(c.qty, c.unit)).join('；')}</span><small>${E(x.note)}</small></div>`).join('')}</div></div>` : ''}
 <div class="section-head compact"><h2>01 · 原料净用量</h2><label class="check-inline"><input type="checkbox" data-change="only-missing" ${onlyMissing ? 'checked' : ''}>只看还没备的</label></div>
 <p class="muted">买好/确认家里有才打勾。菜或份量改变后，相关行会自动取消旧完成状态；展开能看分别怎么处理。</p>
 <div class="shopping-list">${shopping.map(x => `<article class="shop-row" data-shop="${x.id}">${prepCheck('shop', x.id, x.signature, `<b>${E(x.name)}</b><span class="qty">${formatQty(x.qty, x.unit)}</span>`, `${x.pantryHint ? '<span class="owned-hint">你已提到有</span>' : ''}`)}<details><summary>${x.uses.length}处用途 · ${E(x.storage)}</summary><p class="muted">${E(x.note)}</p>${x.uses.map(u => `<p><b>${E(u.title)} · ${formatQty(u.qty, u.unit)}</b><br>${E(u.form)} · ${E(u.pack)}${u.scaling === 'batch' ? ' · 按批保底量，不随半份减半' : ''}</p>`).join('')}</details></article>`).join('') || '<div class="empty">目前都已备好。取消上方筛选可查看全部。</div>'}</div>
 <div class="notice">1茶匙＝5ml量勺容量，不是5g。配方饮用水已列；洗手洗具、家庭泡粉丝/煮面用水、煮饭用水与现场少量补水另带。清单保留净需求，不用为0.3g盐购买新小瓶。</div>
 <h2 class="section-title">02 · 在家预制与分装</h2><p class="muted">“同一组”仅表示放进同一份材料包；是否混匀按该菜步骤。生肉、生食腌汁与即食冷酱不混盒。</p>
 ${p.views.map(r => `<details class="pack-recipe" data-pack-recipe="${r.id}"><summary><b>${E(r.title)}</b><span>约${Math.ceil(r.homeEstimate)}分钟家里准备 · ${fraction(r.portion)}</span></summary><div class="pack-content">${r.prep.map((t, j) => prepCheck('home', r.id + ':' + j, r.signature, E(t))).join('')}<h4>按这道分袋 / 小盒</h4>${p.packs.filter(x => x.recipeId === r.id).map(pack => prepCheck('pack', pack.id, pack.signature, `<b>${E(pack.name)}</b><ul>${pack.rows.map(a => `<li>${E(a.name)} <strong>${formatQty(a.qty, a.unit)}</strong> — ${E(a.form)}${a.stage === '现场' ? ' <em>临用处理</em>' : ''}</li>`).join('')}</ul>`)).join('')}</div></details>`).join('')}
 <div class="panel"><h2>03 · 工具只带并集</h2><div class="equipment">${p.equipment.map(t => `<span>${E(t)}</span>`).join('')}</div><p>这些是所选菜要求的工具，不等于你已经有。至少保留冷藏容器、生熟分区、隔热手套、厨房纸、垃圾袋与清洗用水。</p></div>
 <div class="panel"><h3>到场节奏</h3><p>先安全生火、设生熟区，再按菜单顺序逐道吃。热菜即出即吃，不为了合照攒成一桌；结束后先去残渣、冷却收纳，回家仍正常清洗。</p>${button('去现场操作卡', 'tab', 'data-tab="menu"', 'btn primary')}</div></section>`;
}
function renderReview() {
    return `<section class="section"><span class="eyebrow">50不是50种调味粉</span><h1 class="page-title">配方为什么这样定</h1><p class="intro">旧版40道逐项复核：${db.audit.filter(a => a.status === '合并退役').length}道重复项退役，${db.audit.filter(a => a.status === '重写').length}道实质重写，保留其余并校准。新增${db.recipes.filter(r => !db.audit.some(a => a.newId === r.id)).length}种做法。每张卡都有独特口感、现场动作、材料裁决和来源范围。</p>
 <div class="decision-grid">${db.herbGuide.map(h => `<article class="panel"><h3>${E(h.name)}</h3><p><b>${E(h.decision)}</b></p><p>${E(h.why)}</p><div class="related">${h.recipes.map(id => button(E(findRecipe(id).title), 'detail', `data-id="${id}"`, 'text-btn')).join('')}</div><details><summary>依据</summary><div class="source-links">${sourceLinks(h.sources)}</div></details></article>`).join('')}</div>
 <div class="panel"><h2>如何理解“定稿”</h2>${db.principles.map(t => `<p>${E(t)}</p>`).join('')}</div>
 <details class="panel"><summary>展开旧版40道逐项审查</summary><div class="audit-table">${db.audit.map(a => `<div class="audit-row"><span class="audit-status">${E(a.status)}</span><div><b>${E(a.oldTitle)}</b>${a.newId && findRecipe(a.newId).title !== a.oldTitle ? ` → ${E(findRecipe(a.newId).title)}` : ''}<p>${E(a.reason)}</p>${a.newId ? button('查看定稿', 'detail', `data-id="${a.newId}"`, 'text-btn') : ''}</div></div>`).join('')}</div></details>
 <details class="panel"><summary>研究来源与安全边界 · ${Object.keys(db.sources).length}项</summary><p>食谱来源支持组合/技法；程序中的份量、设备改编与操作安排由本版制定。没有声称在你的炉具上做过实灶试吃。</p>${Object.entries(db.sources).map(([id, s]) => `<div class="source-entry"><a href="${E(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${E(s.title)} ↗</a><p>${E(s.scope)}</p></div>`).join('')}</details>
 <div class="panel"><h2>备份、扩展与迁移</h2><p>完整备份包含菜单、笔记、进度及当前菜谱库。源码中的 <code>data/recipes.json</code> 是正式配方库。导入前校验材料、数量、引用和唯一ID；不执行JSON里的代码。旧版菜单可迁移，但旧鲜干配方库不直接沿用。</p><div class="actions">${button('导出完整备份', 'export-backup')}${button('导入完整备份', 'import-backup', '', 'btn ghost')}${button('导出菜谱库', 'export-library', '', 'btn ghost')}${button('导入菜谱库', 'import-library', '', 'btn ghost')}${button('恢复内置库', 'restore-library', '', 'text-btn')}</div><p>导入库会重算材料并清空进度，保留仍存在的选菜ID与笔记。只在本机保存；修改前先导出。</p><p class="muted">浏览器本地文件是否允许自动记忆由浏览器决定。移动端聊天预览器可能禁用脚本；请在浏览器打开，或按源码README通过局域网访问。</p></div></section>`;
}
function renderDialog() {
    const r = recipeView(db, dialogId, state), selected = state.selected.includes(r.id), nextViews = selectedViews(db, state), position = nextViews.findIndex(x => x.id === r.id);
    const currentScroll = dialog.querySelector('.dialog-body')?.scrollTop ?? 0;
    dialog.innerHTML = `<div class="dialog-header"><div><span class="eyebrow">${E(r.category)} · ${E(r.technique)}</span><h2>${E(r.title)}</h2></div>${button('×', 'close-dialog', 'aria-label="关闭操作卡"', 'close-btn')}</div>
 <div class="dialog-body"><p class="dialog-taste">${E(r.taste)} <span>／ ${E(r.texture)}</span></p><div class="dialog-control">${toggleButton(r.id)}${portionControl(r.id, 'dialog')}<span>${state.people}人 · ${r.batches}批</span></div>
 <div class="recipe-promise"><b>这道真正玩的</b><p>${E(r.fun)}</p><small>${E(r.why)}</small></div>
 <div class="tag-row"><span>现场约${r.totalEstimate}分钟</span><span>主动${r.activeEstimate}分钟</span><span>在家约${Math.ceil(r.homeEstimate)}分钟</span>${r.needsFreezer ? '<span class="cold-tag">持续冷冻</span>' : ''}</div>
 <div class="decision"><h3>已经替你定好的材料</h3>${r.decisions.map(t => `<p>${E(t)}</p>`).join('')}</div>
 <details class="ingredient-detail" open><summary>本菜材料 · 已按${state.people}人 × ${fraction(r.portion)}计算</summary><div class="ingredient-lines">${r.rows.map(a => `<div><b>${E(a.name)}</b><strong>${formatQty(a.qty, a.unit)}</strong><span>${E(a.form)}${a.scaling === 'batch' ? ' · 每批量' : ''}</span></div>`).join('')}</div></details>
 <details class="home-detail"><summary>出发前做完（约${Math.ceil(r.homeEstimate)}分钟）</summary>${r.prep.map(t => `<p>${E(t)}</p>`).join('')}</details>
 <div class="section-head compact"><h3>现场照着做</h3><span class="muted">${r.steps.filter((_, j) => isChecked(state, 'step', r.id + ':' + j, r.signature)).length}/${r.steps.length}完成</span></div>
 <ol class="step-list">${r.steps.map((t, j) => `<li class="${isChecked(state, 'step', r.id + ':' + j, r.signature) ? 'done' : ''}"><label><input type="checkbox" data-change="step" data-id="${r.id}" data-key="${j}" data-sig="${r.signature}" ${isChecked(state, 'step', r.id + ':' + j, r.signature) ? 'checked' : ''}><span class="step-no">${j + 1}</span><span>${E(t)}</span></label></li>`).join('')}</ol>
 <div class="timer-box"><div><b>检查提醒，不是熟度判定</b><p id="timer-readout">未计时</p></div><div class="actions">${[1, 3, 5, 10].map(n => button(`${n}分钟`, 'timer', `data-minutes="${n}" data-id="${r.id}"`, 'btn ghost small')).join('')}${button('停止', 'stop-timer', '', 'text-btn')}</div><small>页面需保持打开；切到后台/锁屏可能延迟提示。回到页面按截止时间校准，不保证后台闹钟。</small></div>
 <div class="notice"><b>防翻车</b><p>${E(r.tip)}</p><p>${E(r.batchNote)}</p></div><p><b>工具：</b>${E(r.equipment.join('、'))}</p><p class="muted">${E(r.hold)}</p>
 <label class="notes-label">给下次留句话<textarea data-change="note" data-id="${r.id}" maxlength="3000" placeholder="记录真实口味、火力与下次想改的地方…">${E(state.notes[r.id] ?? '')}</textarea></label>
 <details class="sources-detail"><summary>原方依据与本版改编边界</summary><p>${E(r.origin)}</p>${r.sources.map(id => `<div class="source-entry"><a href="${E(safeUrl(db.sources[id].url))}" target="_blank" rel="noopener noreferrer">${E(db.sources[id].title)} ↗</a><p>${E(db.sources[id].scope)}</p></div>`).join('')}</details></div>
 <div class="dialog-footer"><span>${E(r.technique)} · ${E(r.moment)}</span>${selected && position >= 0 && position < nextViews.length - 1 ? button('下一道 →', 'detail', `data-id="${nextViews[position + 1].id}"`, 'btn primary') : button('回到菜单', 'close-dialog', '', 'btn')}</div>`;
    dialog.querySelector('.dialog-body').scrollTop = currentScroll;
    updateTimer();
}
function openRecipe(id) { if (!findRecipe(id))
    return; const switched = dialogId !== id; dialogId = id; renderDialog(); if (!dialog.open)
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
function switchTab(name) { if (!['browse', 'menu', 'prep', 'review'].includes(name))
    return; tab = name; render(); window.scrollTo({ top: 0, behavior: 'instant' }); }
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
        category = b.dataset.value;
        render();
    }
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
        download(`火边完整备份-${dateName()}.json`, JSON.stringify(makeBackup(db, state), null, 2));
    else if (a === 'export-library')
        download('火边定稿菜谱库-v2.json', JSON.stringify(db, null, 2));
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
        download('火边本机数据救援.json', JSON.stringify({ stateRaw: failedRaw || readStore(STORE + '-recovery') || readStore(STORE), libraryRaw: readStore(LIB) }, null, 2));
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
    if (a === 'portion') {
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
dialog.addEventListener('close', () => { dialogId = null; });
dialog.addEventListener('click', e => { if (e.target === dialog) {
    const r = dialog.getBoundingClientRect();
    if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
        closeDialog();
} });
document.addEventListener('visibilitychange', updateTimer);
timerTick = setInterval(updateTimer, 1000);
window.addEventListener('pagehide', () => { persist(); clearInterval(timerTick); });
window.addEventListener('pageshow', () => { clearInterval(timerTick); timerTick = setInterval(updateTimer, 1000); updateTimer(); });
render();
