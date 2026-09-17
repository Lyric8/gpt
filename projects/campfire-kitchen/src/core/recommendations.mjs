import { recipeView } from '../engine.mjs';
/** Deterministic bounded greedy sets; only ready recipes enter. Not a nutritional/quantity optimizer. */
export function suggestMeals(db, matches, state) {
  const ready = matches.filter(m => m.ready).map(m => recipeView(db, m.recipe.id, state, 1));
  if (ready.length < 2) return [];
  const presets = [
    {id:'balanced', title:'换着口味吃', max:4, budget:65, speed:0.4, variety:18},
    {id:'quick', title:'少忙一点', max:3, budget:35, speed:2.3, variety:10},
    {id:'together', title:'一起动手吃', max:4, budget:65, speed:0.6, variety:13},
  ];
  const results = [], signatures = new Set();
  for (const preset of presets) {
    const chosen = [], mains = new Set(), categories = new Set(), profiles = new Set(), textures = new Set(), tools = new Set();
    let active = 0;
    while (chosen.length < preset.max) {
      const candidates = ready.filter(r => !chosen.some(c => c.id === r.id) && !mains.has(r.main) && active + r.activeEstimate <= preset.budget);
      if (!candidates.length) break;
      const score = r => (categories.has(r.category) ? 0 : preset.variety) + (profiles.has(r.profile) ? 0 : 5) +
        (textures.has(r.textureFamily) ? 0 : 4) + (r.light && !chosen.some(c => c.light) ? 8 : 0) +
        (preset.id === 'balanced' && !chosen.length && db.ingredients[r.main]?.protein ? 18 : 0) +
        (preset.id === 'balanced' && r.category === '主食' && !categories.has('主食') ? 12 : 0) +
        (preset.id === 'together' && r.interaction === '动手' ? 14 : 0) -
        r.activeEstimate * preset.speed - r.equipment.filter(t => !tools.has(t)).length * 1.2;
      candidates.sort((a,b) => score(b)-score(a) || a.rank-b.rank || a.id.localeCompare(b.id));
      const selected = candidates[0];
      chosen.push(selected); mains.add(selected.main); categories.add(selected.category); profiles.add(selected.profile);
      textures.add(selected.textureFamily); selected.equipment.forEach(t => tools.add(t)); active += selected.activeEstimate;
    }
    if (chosen.length < 2) continue;
    chosen.sort((a,b) => a.rank-b.rank || a.id.localeCompare(b.id));
    const signature = chosen.map(r => r.id).sort().join('|');
    if (signatures.has(signature)) continue;
    signatures.add(signature);
    const ingredientCounts = new Map();
    chosen.forEach(r => new Set(r.ingredients.map(i => i.ingredient)).forEach(id => ingredientCounts.set(id,(ingredientCounts.get(id) ?? 0)+1)));
    const shared = [...ingredientCounts].filter(([,n]) => n>1).length;
    const reasons = [`${categories.size}类菜品、${textures.size}种口感`, `现场主动操作约${Math.ceil(active)}分钟`];
    if (chosen.some(r => r.light)) reasons.push('有清口菜穿插');
    if (shared) reasons.push(`${shared}种食材可复用`);
    results.push({id:preset.id,title:preset.title,recipes:chosen,active:Math.ceil(active),reasons,
      note:'每道按当前人数 × 1份组合；只核对拥有种类，合计用量、冷链与生火条件仍须在备料页确认。'});
  }
  return results;
}
