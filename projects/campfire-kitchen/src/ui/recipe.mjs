import { safeUrl } from '../engine.mjs';
import { recipeView, selectedViews, formatQty, isChecked } from '../engine.mjs';
import { E, button, fraction, photoHTML, photoCredit } from './components.mjs';
export function renderRecipeDialog(ctx) {
    const {db,state,dialogId,dialog,toggleButton,portionControl,updateTimer,photos} = ctx;
    const r = recipeView(db, dialogId, state), selected = state.selected.includes(r.id), nextViews = selectedViews(db, state), position = nextViews.findIndex(x => x.id === r.id);
    const sameRecipe=dialog.dataset.recipeId===r.id;
    const active=sameRecipe&&dialog.contains(document.activeElement)?document.activeElement:null;
    const keys=['data-change','data-action','data-id','data-key','data-scope','data-minutes','aria-label'];
    const focusSelector=active?active.tagName.toLowerCase()+keys.filter(k=>active.hasAttribute(k)).map(k=>`[${k}="${CSS.escape(active.getAttribute(k))}"]`).join(''):'';
    const details=sameRecipe?new Map([...dialog.querySelectorAll('details')].map(d=>[d.className,d.open])):new Map();
    const currentScroll=sameRecipe?(dialog.querySelector('.dialog-body')?.scrollTop??0):0;
    dialog.dataset.recipeId=r.id;
    dialog.innerHTML = `<div class="dialog-header"><div><span class="eyebrow">${E(r.category)} · ${E(r.technique)}</span><h2>${E(r.title)}</h2></div>${button('×', 'close-dialog', 'aria-label="关闭操作卡"', 'close-btn')}</div>
 <div class="dialog-body"><div class="detail-photo">${photoHTML(photos,r.id,'dish-photo',true)}</div>${photoCredit(photos,r.id)}<p class="dialog-taste">${E(r.taste)} <span>／ ${E(r.texture)}</span></p><div class="dialog-control">${toggleButton(r.id)}${portionControl(r.id, 'dialog')}<span>${state.people}人 · ${r.batches}批</span></div>
 <div class="recipe-promise"><b>这道真正玩的</b><p>${E(r.fun)}</p><small>${E(r.why)}</small></div>
 <div class="tag-row"><span>现场约${r.totalEstimate}分钟</span><span>主动${r.activeEstimate}分钟</span><span>在家约${Math.ceil(r.homeEstimate)}分钟</span>${r.needsFreezer ? '<span class="cold-tag">持续冷冻</span>' : ''}</div>
 <details class="decision"><summary>配方的材料为什么这样定</summary>${r.decisions.map(t => `<p>${E(t)}</p>`).join('')}</details>
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
    dialog.querySelectorAll('details').forEach(d=>{if(details.has(d.className))d.open=details.get(d.className);});
    if(focusSelector)dialog.querySelector(focusSelector)?.focus({preventScroll:true});
    updateTimer();
}
