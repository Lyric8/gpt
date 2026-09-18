import { escapeHTML, safeUrl } from '../engine.mjs';
export const E = escapeHTML;
export function button(label, action, attrs = '', cls = 'btn') {
  return `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${label}</button>`;
}
export function metric(value,label) { return `<div class="metric"><strong>${E(value)}</strong><span>${E(label)}</span></div>`; }
export function fraction(n) { return ({'0.25':'¼份','0.5':'半份','0.75':'¾份',1:'1份',1.5:'1½份',2:'2份',3:'3份',4:'4份'})[n] ?? `${n}份`; }
export function getPhoto(photos,id) { return photos.schemaVersion===2 ? photos.library[photos.refs[id]] : photos[id]; }
export function photoHTML(photos,id,cls = 'dish-photo',eager = false) {
  const photo = getPhoto(photos,id);
  if (!photo || !/^data:image\/webp;base64,[A-Za-z0-9+/=]+$/.test(photo.src)) return '<div class="photo-empty"><span aria-hidden="true">火边</span>暂无对应实拍</div>';
  return `<img class="${cls}" src="${photo.src}" alt="${E(photo.alt)}" width="${photo.width || 640}" height="${photo.height || 420}" loading="${eager ? 'eager':'lazy'}" decoding="async">`;
}
export function photoCredit(photos,id) {
  const p = getPhoto(photos,id);
  if (!p) return '';
  return `<details class="photo-credit"><summary>${p.kind==='ingredient'?'食材实拍':'同类菜品参考图'} · 来源与许可</summary><p>${E(p.note)}；并非本配方的实拍成品。</p><p>${E(p.author)} · <a href="${E(safeUrl(p.source))}" target="_blank" rel="noopener noreferrer">原图</a> · <a href="${E(safeUrl(p.licenseUrl))}" target="_blank" rel="noopener noreferrer">${E(p.license)}</a></p></details>`;
}
export function categoryChips(index,selected,action = 'scope') {
  const counts=new Map();index.recipes.forEach(e=>counts.set(e.recipe.category,(counts.get(e.recipe.category)||0)+1));
  return `<div class="chips" role="group" aria-label="${action==='scope'?'菜谱分类，可多选':'菜谱分类'}">${button('全部',action,'data-value="" aria-pressed="'+!selected.length+'"',`chip ${!selected.length?'active':''}`)}${index.categories.map(c => button(`${E(c)} <small>${counts.get(c)||0}</small>`,action,`data-value="${E(c)}" aria-pressed="${selected.includes(c)}"`,`chip ${selected.includes(c)?'active':''}`)).join('')}</div>`;
}
export function pager(view,action) {
  if (view.pages<=1) return '';
  return `<nav class="pagination" aria-label="菜谱分页">${button('← 上一页',action,`data-page="${view.page-1}" ${view.page===1?'disabled':''}`,'btn ghost')}<span role="status">第 <b>${view.page}</b> / ${view.pages} 页</span>${button('下一页 →',action,`data-page="${view.page+1}" ${view.page===view.pages?'disabled':''}`,'btn ghost')}</nav>`;
}
export function recipeCards(recipes,ctx,matches = new Map()) {
  const {db,state,photos} = ctx;
  if (!recipes.length) return '<div class="empty"><h3>没有找到这道菜</h3><p>试试食材名，或切回全部分类。</p></div>';
  return recipes.map((r,i) => {
    const selected = state.selected.includes(r.id), m = matches.get(r.id), photo=getPhoto(photos,r.id);
    const primary = [...new Set([r.main, ...r.ingredients.map(a=>a.ingredient).filter(id=>!db.ingredients[id].pantryHint)])].slice(0,3);
    const missing = m ? [...m.missingIngredients.map(id=>db.ingredients[id].name),...m.missingTools,m.needsFreezer?'持续≤-18℃冷冻条件':''].filter(Boolean) : [];
    return `<article class="recipe-card ${selected?'is-selected':''}" data-card="${E(r.id)}" ${m?`data-match="${m.status}"`:''}>
      <button type="button" class="photo-button" data-action="detail" data-id="${E(r.id)}" aria-label="查看${E(r.title)}做法">${photoHTML(photos,r.id,'dish-photo',i<3)}${photo?`<span class="photo-label">${photo.kind==='ingredient'?'食材参考':'实拍参考'}</span>`:''}</button>
      <div class="card-content"><div class="card-meta"><span>${E(r.category)}</span><span>现场约 ${r.totalMinutes} 分钟</span></div>
      <button type="button" class="card-title" data-action="detail" data-id="${E(r.id)}"><h3>${E(r.title)}</h3></button>
      <p class="card-ingredients">${primary.map(id=>E(db.ingredients[id].name)).join(' · ')}</p>
      ${m?`<div class="match-note ${m.ready?'ready':'missing'}"><b>${m.ready?'✓ 食材与工具齐全':m.status==='equipment'?'缺工具或冷冻条件':`缺 ${m.missingIngredients.length} 种食材`}</b>${missing.length?`<details><summary>查看缺项</summary><p>${E(missing.join('、'))}</p></details>`:''}</div>`:''}
      <div class="card-bottom">${button(selected?'✓ 已选':'+ 加入菜单','toggle',`data-id="${E(r.id)}" aria-label="${selected?'从菜单移除':'加入菜单：'}${E(r.title)}" aria-pressed="${selected}"`,`btn ${selected?'selected':''}`)}</div></div></article>`;
  }).join('');
}
