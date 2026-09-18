import { safeUrl, recipeView, selectedViews, formatQty, isChecked } from '../engine.mjs';
import { E, button, fraction, photoHTML, photoCredit } from './components.mjs';
export function renderRecipeDialog(ctx) {
  const {db,state,dialogId,dialog,toggleButton,portionControl,photos} = ctx;
  const r=recipeView(db,dialogId,state);if(!r)return;
  const selected=state.selected.includes(r.id), next=selectedViews(db,state), position=next.findIndex(x=>x.id===r.id);
  const same=dialog.dataset.recipeId===r.id, active=same&&dialog.contains(document.activeElement)?document.activeElement:null;
  const keys=['data-change','data-action','data-id','data-key','data-scope','aria-label'];
  const focus=active?active.tagName.toLowerCase()+keys.filter(k=>active.hasAttribute(k)).map(k=>`[${k}="${CSS.escape(active.getAttribute(k))}"]`).join(''):'';
  const expanded=same?new Map([...dialog.querySelectorAll('details')].map(d=>[d.className,d.open])):new Map();
  const scroll=same?(dialog.querySelector('.dialog-body')?.scrollTop??0):0;
  dialog.dataset.recipeId=r.id;
  dialog.innerHTML=`<div class="dialog-header"><div><span class="eyebrow">${E(r.category)}</span><h2 id="recipe-dialog-title">${E(r.title)}</h2></div>${button('×','close-dialog','aria-label="关闭做法"','close-btn')}</div>
  <div class="dialog-body"><div class="recipe-overview"><div class="detail-photo">${photoHTML(photos,r.id,'dish-photo',true)}${photoCredit(photos,r.id)}</div><div><p class="recipe-method">${E(r.technique)}</p><p class="recipe-estimate">现场约 ${r.totalEstimate} 分钟${r.needsFreezer?' · 需持续冷冻':''}</p><div class="dialog-control">${toggleButton(r.id)}${portionControl(r.id,'dialog')}<span>按 ${state.people} 人计算 · ${r.batches} 批</span></div></div></div>
  ${r.fireSetup?`<section class="fire-instruction"><h3>火怎么摆</h3><p>${E(r.fireSetup)}</p></section>`:''}
  <details class="ingredient-detail" open><summary>材料 · ${state.people} 人 × ${fraction(r.portion)}</summary><div class="ingredient-lines">${r.rows.map(a=>`<div><b>${E(a.name)}</b><strong>${formatQty(a.qty,a.unit)}</strong>${a.form&&a.form!=='按准备步骤处理'?`<span>${E(a.form)}${a.scaling==='batch'?' · 每批量':''}</span>`:''}</div>`).join('')}</div></details>
  <details class="home-detail" open><summary>提前准备</summary>${r.prep.map(t=>`<p>${E(t)}</p>`).join('')}</details>
  <section class="cooking-section"><div class="section-head compact"><h3>上火做法</h3><span class="muted">${r.steps.filter((_,j)=>isChecked(state,'step',r.id+':'+j,r.signature)).length}/${r.steps.length} 步完成</span></div><ol class="step-list">${r.steps.map((t,j)=>`<li class="${isChecked(state,'step',r.id+':'+j,r.signature)?'done':''}"><label><input type="checkbox" aria-label="完成第 ${j+1} 步" data-change="step" data-id="${E(r.id)}" data-key="${j}" data-sig="${E(r.signature)}" ${isChecked(state,'step',r.id+':'+j,r.signature)?'checked':''}><span class="step-no">${j+1}</span><span>${E(t)}</span></label></li>`).join('')}</ol></section>
  ${r.completion?`<section class="doneness"><h3>什么时候算做好</h3><p>${E(r.completion)}</p></section>`:''}
  <section class="serving"><h3>怎么吃</h3><p>${E(r.serving||r.fun)}</p></section>
  <details class="tools-detail"><summary>工具与保存</summary><p>${E(r.equipment.join('、'))}</p><p>${E(r.hold)}</p>${r.id.startsWith('v4-')?'':`<p>${E(r.tip)}</p><p>${E(r.batchNote)}</p>`}</details>
  <label class="notes-label">我的笔记<textarea data-change="note" data-id="${E(r.id)}" maxlength="3000" placeholder="记下这次的口味、火力和下次想改的地方">${E(state.notes[r.id]??'')}</textarea></label>
  <details class="sources-detail"><summary>配方说明与依据</summary><p>${E(r.origin)}</p>${r.sources.map(id=>db.sources[id]?`<div class="source-entry"><a href="${E(safeUrl(db.sources[id].url))}" target="_blank" rel="noopener noreferrer">${E(db.sources[id].title)}</a><p>${E(db.sources[id].scope)}</p></div>`:'').join('')}</details></div>
  <div class="dialog-footer"><span>按熟度判断，不靠倒计时</span>${selected&&position>=0&&position<next.length-1?button('下一道 →','detail',`data-id="${E(next[position+1].id)}"`,'btn primary'):button('关闭做法','close-dialog','','btn')}</div>`;
  dialog.setAttribute('aria-labelledby','recipe-dialog-title');
  dialog.querySelector('.dialog-body').scrollTop=scroll;
  dialog.querySelectorAll('details').forEach(d=>{if(expanded.has(d.className))d.open=expanded.get(d.className);});
  if(focus)dialog.querySelector(focus)?.focus({preventScroll:true});
}
