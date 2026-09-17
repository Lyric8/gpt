import { E, button, categoryChips, recipeCards, photoHTML } from './components.mjs';
import { inventoryCandidates } from '../core/pantry.mjs';
export function pantryView(ctx) {
  const {index,inventory,pantryQuery,matchFilter,matches,meals,state} = ctx;
  const candidates = inventoryCandidates(index,inventory.categories,pantryQuery);
  const counts = {ready:0,ingredients:0,equipment:0,all:matches.length};
  matches.forEach(m=>counts[m.status]++);
  const shown = matches.filter(m=>matchFilter==='all'||m.status===matchFilter).sort((a,b)=>a.missingCount-b.missingCount||a.recipe.rank-b.recipe.rank);
  const groupHTML = (items,kind) => {
    const groups = [...new Set(items.map(i=>i.group))];
    return groups.map((group,number) => {
      const rows = items.filter(i=>i.group===group), owned = new Set(inventory[kind]);
      return `<details class="inventory-group" data-keep="${kind}:${E(group)}" ${number===0&&!pantryQuery?'open':''} ${pantryQuery?'open':''}><summary><span>${E(group)}</span><small>${rows.filter(i=>owned.has(i.id)).length} / ${rows.length}</small></summary><div class="group-actions">${button('本组全选','inventory-group',`data-kind="${kind}" data-group="${E(group)}" data-mode="select"`,'text-btn')}${button('取消本组','inventory-group',`data-kind="${kind}" data-group="${E(group)}" data-mode="clear"`,'text-btn')}</div><div class="inventory-options">${rows.map(i=>`<label class="inventory-option ${owned.has(i.id)?'checked':''}"><input type="checkbox" data-change="inventory" data-kind="${kind}" data-id="${E(i.id)}" ${owned.has(i.id)?'checked':''}><span>${E(i.name)}${kind==='tools'&&i.note?`<small>${E(i.note)}</small>`:''}</span></label>`).join('')}</div></details>`;
    }).join('') || '<p class="muted">这个范围内没有匹配候选。</p>';
  };
  return `<section class="section pantry-page"><div class="section-head"><div><span class="eyebrow">不必为一顿饭，再买一箱调料</span><h1 class="page-title">我有这些，能做什么？</h1><p class="muted">先缩小菜谱范围，再勾选已有食材和工具。结果会随勾选更新。</p></div></div>
    <section class="scope-box" aria-labelledby="scope-title"><h2 id="scope-title">想做哪类菜 <span>可多选</span></h2>${categoryChips(index,inventory.categories)}<p>范围：${E(inventory.categories.join('、')||'全部菜谱')} · 换分类只收起无关候选，不清空已有库存。</p></section>
    <div class="pantry-layout"><aside class="inventory-panel" aria-label="我已有的食材与工具"><div class="inventory-top"><h2>勾选我已有的</h2><span id="inventory-count">${inventory.ingredients.length}种食材 · ${inventory.tools.length}件工具</span><label class="search-box"><span aria-hidden="true">⌕</span><input id="pantry-search" type="search" placeholder="在候选里找食材、工具" value="${E(pantryQuery)}" aria-label="搜索食材和工具候选"></label></div>
    <div class="inventory-scroll"><h3 class="inventory-subhead">食材 <small>调味品也请勾选</small></h3>${groupHTML(candidates.ingredients,'ingredients')}<h3 class="inventory-subhead">工具 <small>按实际条件核对</small></h3>${groupHTML(candidates.tools,'tools')}<label class="inventory-option freezer"><input type="checkbox" data-change="freezer" ${state.hasFreezer?'checked':''}><span>本次有持续≤-18℃冷冻条件<small>车载冷藏、保冷箱不自动等于冷冻。</small></span></label></div>
    <div class="inventory-bottom">${button('清空库存勾选','clear-inventory','','text-btn')}<small>已有 ≠ 本次已称量、已装车</small></div></aside>
    <section class="pantry-results" id="inventory-results" tabindex="-1" aria-labelledby="results-title"><div class="results-heading"><div><span class="eyebrow">按你现有的来</span><h2 id="results-title">现在可做 <strong>${counts.ready}</strong> 道</h2></div><span class="muted" role="status" aria-live="polite">范围内共 ${matches.length} 道</span></div>
    <div class="match-filters" role="group" aria-label="匹配结果类型">${[['ready','完全具备'],['ingredients','缺食材'],['equipment','缺工具 / 冷冻'],['all','全部']].map(([id,label])=>button(`${label} <b>${counts[id]}</b>`,'match-filter',`data-value="${id}" aria-pressed="${matchFilter===id}"`,`match-filter ${matchFilter===id?'active':''}`)).join('')}</div>
    ${meals.length?`<details class="meal-ideas" data-keep="meal-ideas" open><summary>这些食材，可以这样组成一顿 <small>${meals.length}套建议</small></summary><div class="meal-idea-grid">${meals.map(m=>`<article class="meal-idea"><h3>${E(m.title)}</h3><div class="meal-idea-photos">${m.recipes.slice(0,3).map(r=>photoHTML(ctx.photos,r.id,'meal-thumb')).join('')}</div><p>${m.recipes.map(r=>E(r.title)).join(' + ')}</p><small>${E(m.reasons.join(' · '))}</small>${button('加入这一组','apply-meal',`data-id="${m.id}"`,'btn')}${m.id==='balanced'?'<span class="muted">荤素/主食按当前可做范围取舍</span>':''}</article>`).join('')}</div><p class="quantity-note">${E(meals[0].note)}</p></details>`:''}
    ${!shown.length?`<div class="empty pantry-empty"><span class="empty-mark" aria-hidden="true">＋</span><h3>${!inventory.ingredients.length&&!inventory.tools.length?'从左侧（手机上方）勾选开始':'这个筛选下还没有菜谱'}</h3><p>${matchFilter==='ready'?'食材与工具全部匹配，菜谱才会出现在这里。盐、油等基础料不会默认算有。':'换个分类或匹配类型看看，已有勾选会保留。'}</p>${matchFilter==='ready'?button('查看还差什么','match-filter','data-value="all"','btn ghost'):''}</div>`:`<div class="recipe-grid pantry-grid" id="pantry-list">${recipeCards(shown.map(m=>m.recipe),ctx,new Map(shown.map(m=>[m.recipe.id,m])))}</div>`}
    <p class="quantity-note">匹配仅说明品类与工具条件具备，不保证存量足够或无需生火。冷链、生熟分离与安全条件仍按操作卡确认。</p></section></div></section>`;
}
