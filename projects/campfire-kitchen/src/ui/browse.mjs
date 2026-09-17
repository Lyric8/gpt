import { E, button, photoHTML, categoryChips, recipeCards } from './components.mjs';
export function browseView(ctx) {
  const {db,index,search,category,experience,freshIdeas,recipes,photos} = ctx;
  return `<section class="browse-hero"><div><h1>先看看，想吃什么。</h1><span class="hero-foot">${db.recipes.length} 道菜谱 · 两人分享小份为基准</span></div>${button('用现有食材找菜 →','tab','data-tab="pantry"','btn primary hero-shortcut')}</section>
    <section class="section catalog" aria-label="浏览与筛选菜谱">
    <div class="search-row"><label class="search-box"><span aria-hidden="true">⌕</span><input id="recipe-search" type="search" placeholder="搜菜名或食材，比如：牛肉、玉米、米饭" value="${E(search)}" aria-label="搜索菜谱"></label><details class="extra-filter" data-keep="browse-filters"><summary>更多筛选</summary><div><label>操作体验 <select id="experience-filter" aria-label="操作体验筛选" data-change="experience">${['全部','动手','轻操作','保底'].map(x=>`<option ${experience===x?'selected':''}>${x}</option>`).join('')}</select></label><label class="check-inline"><input type="checkbox" data-change="fresh-ideas" ${freshIdeas?'checked':''}>最近三次没做过</label></div></details></div>
    ${categoryChips(index,category==='全部'?[]:[category],'category')}
    <details class="preset-disclosure" data-keep="presets"><summary>不想从头搭配？看看 ${db.presets.length} 套现成菜单 <span>展开选一桌</span></summary><div class="preset-grid">${db.presets.map(p=>`<button type="button" class="preset-card" data-action="preset" data-id="${E(p.id)}"><div class="preset-photos">${Object.keys(p.selected).slice(0,3).map(id=>photoHTML(photos,id,'preset-photo')).join('')}</div><strong>${E(p.name)}</strong><span>${E(p.note)}</span><small>${Object.keys(p.selected).length}道 · 点选前确认</small></button>`).join('')}</div></details>
    <p class="catalog-count" id="recipe-count" role="status">${recipes.length} / ${db.recipes.length} 道</p>
    <div class="recipe-grid" id="catalog-list">${recipeCards(recipes,ctx)}</div></section>`;
}
