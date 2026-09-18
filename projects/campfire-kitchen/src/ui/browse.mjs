import { E, button, photoHTML, categoryChips, recipeCards, pager } from './components.mjs';
import { paginate } from '../core/pagination.mjs';
export function catalogResults(ctx) {
  const page=paginate(ctx.recipes,ctx.browsePage);
  return `<div class="catalog-count" id="recipe-count" role="status" tabindex="-1">${page.total} 道菜${page.total?` <span>· 显示 ${page.first}–${page.last} 道</span>`:''}</div><div class="recipe-grid" id="catalog-list">${recipeCards(page.items,ctx)}</div>${pager(page,'browse-page')}`;
}
export function browseView(ctx) {
  const {db,index,search,category,experience,freshIdeas,photos} = ctx;
  return `<section class="browse-hero"><div><span class="eyebrow">${db.recipes.length} 道露营菜谱</span><h1>串烤、烟熏，一顿玩开。</h1><p>选一道看做法，选几道排成一桌。</p></div>${button('用现有食材找菜 →','tab','data-tab="pantry"','btn primary hero-shortcut')}</section>
    <aside class="fire-shortcut"><div><b>竹炭供热，苹果木增香</b><span>双区火怎么摆、木块什么时候加，一页说清。</span></div>${button('怎么用 →','tab','data-tab="fire"','text-btn')}</aside>
    <section class="section catalog" aria-label="浏览与筛选菜谱">
    <div class="search-row"><label class="search-box"><span aria-hidden="true">⌕</span><input id="recipe-search" type="search" placeholder="搜菜名、食材或玩法：羊肉串、苹果木" value="${E(search)}" aria-label="搜索菜谱"></label><details class="extra-filter" data-keep="browse-filters"><summary>其他筛选</summary><div><label>操作量 <select id="experience-filter" aria-label="操作量筛选" data-change="experience">${[['全部','不限'],['动手','想多动手'],['轻操作','简单操作'],['保底','备选快手菜']].map(([v,label])=>`<option value="${v}" ${experience===v?'selected':''}>${label}</option>`).join('')}</select></label><label class="check-inline"><input type="checkbox" data-change="fresh-ideas" ${freshIdeas?'checked':''}>排除最近三次做过的菜</label></div></details></div>
    ${categoryChips(index,category==='全部'?[]:[category],'category')}
    <div id="catalog-results">${catalogResults(ctx)}</div>
    <details class="preset-disclosure" data-keep="presets"><summary>${db.presets.length} 套组合菜单 <span>直接选一桌</span></summary><div class="preset-grid">${db.presets.map(p=>`<button type="button" class="preset-card" data-action="preset" data-id="${E(p.id)}"><div class="preset-photos">${Object.keys(p.selected).slice(0,3).map(id=>photoHTML(photos,id,'preset-photo')).join('')}</div><strong>${E(p.name)}</strong><span>${E(p.note)}</span><small>${Object.keys(p.selected).length} 道菜</small></button>`).join('')}</div></details>
    <p class="quantity-note">时间为排餐估计，不含生火与提前腌制；份量可在菜单中调整。图片为同类菜品或食材参考。</p></section>`;
}
