import { safeUrl } from '../engine.mjs';
import { E, button } from './components.mjs';
export function settingsView(ctx) {
  const {db,findRecipe,sourceLinks}=ctx;
  return `<section class="section"><h1 class="page-title">资料与备份</h1><p class="intro">当前菜谱库 ${db.recipes.length} 道。菜单、库存和笔记只保存在这个浏览器中。</p>
  <section class="panel"><h2>保存我的菜单和库存</h2><p>完整备份包含当前菜谱库、选菜、份量、食材与工具勾选、笔记和进度。换设备或清理浏览器前先导出。</p><div class="actions">${button('导出完整备份','export-backup','','btn primary')}${button('导入完整备份','import-backup','','btn ghost')}</div></section>
  <details class="panel"><summary>管理菜谱库</summary><p>导入后校验全部数量与引用，保留仍存在的选菜和笔记，并清空原有备料进度。修改前先导出。</p><div class="actions">${button('导出菜谱库','export-library')}${button('导入菜谱库','import-library','','btn ghost')}${button('恢复 V4 内置 300 道','restore-library','','btn ghost')}</div><p>开发源文件在 data/catalog，构建时校验并汇总；导出的 JSON 是完整菜谱库。</p></details>
  <section class="panel"><h2>如何使用这些配方</h2><p>用量以两人分享为起点，可在菜单里调整人数和每道份量。分钟数是排餐估计，不替代熟度与中心温度判断；这些配方没有逐一在你的炉具上做过实灶验证。</p><p>图片为同类菜品或食材参考，不是每道配方的成品实拍。每张图的摄影者、来源与许可可在做法页展开查看。</p>${button('查看炭火与烟熏指南 →','tab','data-tab="fire"','text-btn')}</section>
  <details class="panel"><summary>安全与配方依据 · ${Object.keys(db.sources).length} 项</summary>${Object.values(db.sources).map(s=>`<div class="source-entry"><a href="${E(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">${E(s.title)}</a><p>${E(s.scope)}</p></div>`).join('')}</details>
  <details class="panel"><summary>香草使用说明</summary>${db.herbGuide.map(h=>`<article><h3>${E(h.name)}</h3><p>${E(h.decision)}</p><p>${E(h.why)}</p><div class="related">${h.recipes.filter(id=>findRecipe(id)).map(id=>button(E(findRecipe(id).title),'detail',`data-id="${E(id)}"`,'text-btn')).join('')}</div><div class="source-links">${sourceLinks(h.sources)}</div></article>`).join('')}</details>
  <details class="panel"><summary>历史配方调整记录</summary>${db.audit.map(a=>`<div class="audit-row"><span class="audit-status">${E(a.status)}</span><div><b>${E(a.oldTitle)}</b><p>${E(a.reason)}</p>${a.newId&&findRecipe(a.newId)?button('查看当前做法','detail',`data-id="${E(a.newId)}"`,'text-btn'):''}</div></div>`).join('')}</details></section>`;
}
