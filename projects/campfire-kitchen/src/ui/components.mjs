import { escapeHTML, safeUrl } from '../engine.mjs';
export const E = escapeHTML;
export function button(label, action, attrs = '', cls = 'btn') {
  return `<button type="button" class="${cls}" data-action="${action}" ${attrs}>${label}</button>`;
}
export function metric(value,label) { return `<div class="metric"><strong>${E(value)}</strong><span>${E(label)}</span></div>`; }
export function fraction(n) { return ({'0.25':'¼份','0.5':'半份','0.75':'¾份',1:'1份',1.5:'1½份',2:'2份',3:'3份',4:'4份'})[n] ?? `${n}份`; }
export function photoHTML(photos,id,cls = 'dish-photo',eager = false) {
  const photo = photos[id];
  if (!photo || !/^data:image\/webp;base64,[A-Za-z0-9+/=]+$/.test(photo.src)) return '<div class="photo-empty">这道菜暂无实拍</div>';
  return `<img class="${cls}" src="${photo.src}" alt="${E(photo.alt)}" width="${photo.width || 640}" height="${photo.height || 420}" loading="${eager ? 'eager':'lazy'}" decoding="async">`;
}
export function photoCredit(photos,id) {
  const p = photos[id];
  if (!p) return '';
  return `<details class="photo-credit"><summary>照片来源 · 同类菜品实拍参考</summary><p>${E(p.note)}。照片不是本配方的复刻成果。</p><p>摄影：${E(p.author)} · <a href="${E(safeUrl(p.source))}" target="_blank" rel="noopener noreferrer">查看原图</a> · <a href="${E(safeUrl(p.licenseUrl))}" target="_blank" rel="noopener noreferrer">${E(p.license)}</a></p></details>`;
}
export function categoryChips(index,selected,action = 'scope') {
  return `<div class="chips" role="group" aria-label="${action==='scope'?'菜谱分类，可多选':'菜谱分类'}">${button('全部',action,'data-value="" aria-pressed="'+!selected.length+'"',`chip ${!selected.length?'active':''}`)}${index.categories.map(c => button(`${E(c)} <small>${index.recipes.filter(e=>e.recipe.category===c).length}</small>`,action,`data-value="${E(c)}" aria-pressed="${selected.includes(c)}"`,`chip ${selected.includes(c)?'active':''}`)).join('')}</div>`;
}
export function recipeCards(recipes,ctx,matches = new Map()) {
  const {db,state,photos} = ctx;
  if (!recipes.length) return '<div class="empty"><h3>暂时没有匹配的菜</h3><p>换个关键词或分类；现有勾选不会丢失。</p></div>';
  return recipes.map((r,i) => {
    const selected = state.selected.includes(r.id), m = matches.get(r.id);
    const primary = [...new Set([r.main, ...r.ingredients.map(a=>a.ingredient).filter(id=>!db.ingredients[id].pantryHint)])].slice(0,3);
    const missing = m ? [...m.missingIngredients.map(id=>db.ingredients[id].name),...m.missingTools,m.needsFreezer?'持续≤-18℃冷冻条件':''].filter(Boolean) : [];
    return `<article class="recipe-card ${selected?'is-selected':''}" data-card="${E(r.id)}" ${m?`data-match="${m.status}"`:''}>
      <button type="button" class="photo-button" data-action="detail" data-id="${E(r.id)}" aria-label="查看${E(r.title)}做法">${photoHTML(photos,r.id,'dish-photo',i<3)}<span class="photo-label">同类实拍</span>${selected?'<span class="photo-selected">✓ 已加入这顿</span>':''}</button>
      <div class="card-content"><div class="card-meta"><span>${E(r.category)}</span><span>主动操作 ${r.activeMinutes} 分钟</span></div>
      <button type="button" class="card-title" data-action="detail" data-id="${E(r.id)}"><h3>${E(r.title)}</h3></button>
      <p class="taste">${E(r.taste)}</p><p class="card-ingredients">${primary.map(id=>E(db.ingredients[id].name)).join(' · ')}</p>
      ${m?`<div class="match-note ${m.ready?'ready':'missing'}"><b>${m.ready?'✓ 食材与工具齐备':m.status==='equipment'?'还需工具 / 冷冻条件':`还缺${m.missingIngredients.length}种食材`}</b>${missing.length?`<span>${E(missing.join('、'))}</span>`:'<span>种类匹配；用量在备料页核对</span>'}</div>`:''}
      <div class="card-bottom">${button('看做法','detail',`data-id="${E(r.id)}"`,'text-btn')}${button(selected?'✓ 已加入':'+ 加入这顿','toggle',`data-id="${E(r.id)}" aria-pressed="${selected}"`,`btn ${selected?'selected':''}`)}</div></div></article>`;
  }).join('');
}
