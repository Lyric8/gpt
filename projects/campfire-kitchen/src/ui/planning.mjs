import { buildPlan, formatQty, isChecked } from '../engine.mjs';
import { E, button, metric, fraction, photoHTML } from './components.mjs';
function issueBox(p) { return p.issues.length ? `<div class="issue-grid">${p.issues.map(x => `<div class="issue ${x.level}"><b>${E(x.title)}</b><p>${E(x.detail)}</p></div>`).join('')}</div>` : `<div class="issue good"><b>这桌暂未发现明显重复或超量操作信号</b><p>这是按菜数、味型、口感组、主材和操作量检查，不是对口味或食量的保证。</p></div>`; }
function emptyMenu() { return `<div class="empty"><h2>这顿还没选菜。</h2><p>去挑一道菜或一套菜单。份量和备料会跟着算。</p>${button('去挑菜', 'tab', 'data-tab="browse"', 'btn primary')}</div>`; }
function prepCheck(state, kind, id, sig, label, extra = '') { const yes = isChecked(state, kind, id, sig); return `<label class="task ${yes ? 'done' : ''}"><input type="checkbox" data-change="check" data-kind="${kind}" data-key="${E(id)}" data-sig="${sig}" ${yes ? 'checked' : ''}><span>${label}${extra}</span></label>`; }
export function menuView(ctx) {
    const {db,state,renderPeople,portionControl,onlyMissing,inventory,photos} = ctx;
    const checkRow = (...args) => prepCheck(state,...args);
    const p = buildPlan(db, state);
    return `<section class="section"><div class="section-head"><div><span class="eyebrow">选菜、调份量、排出餐顺序</span><h1 class="page-title">这顿怎么吃</h1></div>${renderPeople()}</div>
 <div class="menu-name"><label>菜单名字<input id="menu-name" maxlength="100" value="${E(state.menuName)}"></label><label class="check-inline"><input type="checkbox" data-change="freezer" ${state.hasFreezer ? 'checked' : ''}>本次有持续≤-18℃冷冻条件</label></div>
 ${!p.views.length ? emptyMenu() : `<div class="metrics">${metric(p.views.length, '道菜')}${metric(state.people, '人用餐')}${metric(p.metrics.active + ' 分', '现场操作合计')}${metric(p.shopping.length, '种原料')}</div><p class="muted small-text">份量改变会重算材料。操作时间为逐道相加，不等于整顿饭的时长。</p><details class="menu-audit" data-keep="menu-audit"><summary>看看搭配与操作提醒 · ${p.issues.length}项</summary>${issueBox(p)}</details>
 <div class="section-head compact"><h2>出餐顺序</h2><div class="actions">${button('清空菜单','clear','','text-btn')}${button('恢复推荐顺序', 'sort', '', 'btn ghost small')}${button('备料清单', 'tab', 'data-tab="prep"', 'btn primary small')}</div></div>
 <p class="muted">用箭头调整出餐顺序。厚肉、烟熏菜先开做，冷菜临吃再拌；不必等所有菜做完才开吃。</p>
 <div class="menu-list">${p.views.map((r, j) => `<article class="menu-item" data-menu-item="${r.id}"><div class="menu-item-photo">${photoHTML(photos,r.id)}<span class="order-no">${String(j + 1).padStart(2, '0')}</span></div><div class="menu-item-main"><h3>${E(r.title)}</h3><p>${E(r.technique)} · ${r.batches} 批 · 现场约 ${r.totalEstimate} 分钟</p><div class="menu-item-tools">${portionControl(r.id, 'menu')}${button('看做法', 'detail', `data-id="${r.id}"`, 'btn small')}</div></div><div class="reorder">${button('↑', 'move', `data-id="${r.id}" data-delta="-1" ${j === 0 ? 'disabled' : ''} aria-label="上移${E(r.title)}"`, 'round-btn')}${button('↓', 'move', `data-id="${r.id}" data-delta="1" ${j === p.views.length - 1 ? 'disabled' : ''} aria-label="下移${E(r.title)}"`, 'round-btn')}${button('移除', 'toggle', `data-id="${r.id}"`, 'text-btn')}</div></article>`).join('')}</div>
 <details class="suggestions" data-keep="menu-more"><summary>再看看互补的菜</summary><h2>搭配参考</h2><p class="muted">结合主材、做法和新增食材筛选；按你的食量取舍。</p><div class="suggestion-grid">${p.suggestions.map(s => `<article><h3>${E(s.title)}</h3><p>${E(s.reasons.join(' · '))}</p><small>较当前清单新增约${s.extraIngredients}种原料（含家中可能已有的基础料）</small>${button('看做法', 'detail', `data-id="${s.id}"`, 'text-btn')}</article>`).join('')}</div></details>
 <div class="panel"><h3>这次做完以后</h3><p>记录这一桌，下一次「最近三次没做过」会避开它。不自动删除菜单。</p>${button('记录这次做过', 'record', '', 'btn')}${state.history.length ? `<span class="muted"> 已记录${state.history.length}次</span>` : ''}</div>`}</section>`;
}
export function prepView(ctx) {
    const {db,state,renderPeople,portionControl,onlyMissing,inventory,photos} = ctx;
    const checkRow = (...args) => prepCheck(state,...args);
    const p = buildPlan(db, state);
    if (!p.views.length)
        return `<section class="section"><h1 class="page-title">备料与分装</h1>${emptyMenu()}</section>`;
    const shopping = p.shopping.filter(x => !onlyMissing || !isChecked(state, 'shop', x.id, x.signature));
    return `<section class="section"><div class="section-head"><div><span class="eyebrow">先核对合计用量，再按菜分装</span><h1 class="page-title">${E(state.menuName)} · 备料</h1></div><div class="actions">${button('导出做法清单', 'export-md', '', 'btn primary')}${button('导出表格', 'export-csv', '', 'btn ghost')}${button('打印', 'print', '', 'btn ghost')}</div></div>
 <div class="prep-summary">${state.people}人 · ${p.views.length}道 · ${p.shopping.length}种原料 <span>净用量不是必须购买的包装大小；库存勾选只表示拥有这种材料；下面仍显示合计净需求，称量完成后再勾选。</span></div>
 ${p.issues.some(x => x.level === 'danger') ? issueBox({ issues: p.issues.filter(x => x.level === 'danger') }) : ''}
 <details class="panel safety"><summary>冷链 / 熟度 / 过敏原（出发前看一次）</summary>${db.safety.map(x => `<p><b>${E(x.title)}</b> ${E(x.text)}</p>`).join('')}<p><b>本次涉及：</b>${E(p.allergens.join('、') || '数据未列出常见过敏原；仍查包装')}。商品配料标签优先。</p></details>
 ${p.procurement.length ? `<div class="panel purchase"><h2>先买多少：需要换算的几项</h2><p>下面是对净材料的采购折算，<b>不是再额外买一份</b>。柠檬同颗取汁取皮；鸡蛋各用途相加；熟饭换算生米。</p><div class="purchase-grid">${p.procurement.map(x => `<div><b>${E(x.name)}</b><strong>约 ${formatQty(x.qty, x.unit)}</strong><span>${x.components.map(c => E(c.name) + ' ' + formatQty(c.qty, c.unit)).join('；')}</span><small>${E(x.note)}</small></div>`).join('')}</div></div>` : ''}
 <div class="section-head compact"><h2>01 · 原料净用量</h2><label class="check-inline"><input type="checkbox" data-change="only-missing" ${onlyMissing ? 'checked' : ''}>只看还没备的</label></div>
 <p class="muted">确认数量足够、已经备好后再勾选。菜或份量改变时，受影响的勾选会自动取消。</p>
 <div class="shopping-list">${shopping.map(x => `<article class="shop-row" data-shop="${x.id}">${checkRow('shop', x.id, x.signature, `<b>${E(x.name)}</b><span class="qty">${formatQty(x.qty, x.unit)}</span>`, `${inventory.ingredients.includes(x.id) ? '<span class="owned-hint">库存已有 · 核对数量</span>' : '<span class="missing-hint">库存未勾选</span>'}`)}<details><summary>${x.uses.length}处用途 · ${E(x.storage)}</summary><p class="muted">${E(x.note)}</p>${x.uses.map(u => `<p><b>${E(u.title)} · ${formatQty(u.qty, u.unit)}</b><br>${E(u.form)} · ${E(u.pack)}${u.scaling === 'batch' ? ' · 按批保底量，不随半份减半' : ''}</p>`).join('')}</details></article>`).join('') || '<div class="empty">目前都已备好。取消上方筛选可查看全部。</div>'}</div>
 <div class="notice">1茶匙＝5ml量勺容量，不是5g。配方饮用水已列；洗手洗具、家庭泡粉丝/煮面用水、煮饭用水与现场少量补水另带。清单保留净需求，不用为0.3g盐购买新小瓶。</div>
 <h2 class="section-title">02 · 在家预制与分装</h2><p class="muted">“同一组”仅表示放进同一份材料包；是否混匀按该菜步骤。生肉、生食腌汁与即食冷酱不混盒。</p>
 ${p.views.map(r => `<details class="pack-recipe" data-pack-recipe="${r.id}"><summary><b>${E(r.title)}</b><span>${fraction(r.portion)} · 腌制、煮熟与冷却按步骤预留时间</span></summary><div class="pack-content">${r.prep.map((t, j) => checkRow('home', r.id + ':' + j, r.signature, E(t))).join('')}<h4>按这道分袋 / 小盒</h4>${p.packs.filter(x => x.recipeId === r.id).map(pack => checkRow('pack', pack.id, pack.signature, `<b>${E(pack.name)}</b><ul>${pack.rows.map(a => `<li>${E(a.name)} <strong>${formatQty(a.qty, a.unit)}</strong> — ${E(a.form)}${a.stage === '现场' ? ' <em>临用处理</em>' : ''}</li>`).join('')}</ul>`)).join('')}</div></details>`).join('')}
 <div class="panel"><h2>03 · 工具与燃料（已去重）</h2><div class="equipment">${p.equipment.map(t => `<span>${E(t)}</span>`).join('')}</div><p>这些是所选菜要求的工具，不等于你已经有。至少保留冷藏容器、生熟分区、隔热手套、厨房纸、垃圾袋与清洗用水。</p></div>
 <div class="panel"><h3>到场节奏</h3><p>先安全生火、设生熟区，再按菜单顺序逐道吃。热菜即出即吃，不为了合照攒成一桌；结束后先去残渣、冷却收纳，回家仍正常清洗。</p>${button('回到菜单看做法', 'tab', 'data-tab="menu"', 'btn primary')}</div></section>`;
}
