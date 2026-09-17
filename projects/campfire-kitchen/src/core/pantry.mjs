/** Inventory uses canonical ingredient IDs and explicit tool capabilities, never name guessing. */
export function makeInventoryIndex(db, equipment) {
  if (!equipment || equipment.schemaVersion!==1 || !Array.isArray(equipment.tools) || !equipment.requirements || typeof equipment.requirements!=='object' || Array.isArray(equipment.requirements)) throw new Error('工具目录结构无效');
  const tools = new Map();
  for (const tool of equipment.tools) {
    if (!tool || ![tool.id,tool.name,tool.group].every(v=>typeof v==='string'&&v.trim()) || !Array.isArray(tool.provides) || !tool.provides.every(v=>typeof v==='string'&&v.trim()) || tools.has(tool.id)) throw new Error('工具定义缺失、重复或能力无效');
    tools.set(tool.id,tool);
  }
  const usedTools = new Set(), usedIngredients = new Set(), categories = [];
  const recipes = db.recipes.map(recipe => {
    if (!categories.includes(recipe.category)) categories.push(recipe.category);
    const ingredientIds = [...new Set(recipe.ingredients.map(row => row.ingredient))];
    ingredientIds.forEach(id => usedIngredients.add(id));
    const requirements = recipe.equipment.map(label => {
      // Imported catalogs can introduce tools: keep an exact requirement rather than silently ignoring it.
      const clauses = equipment.requirements[label] ?? [[`custom:${label}`]];
      if (!Array.isArray(clauses) || !clauses.length) throw new Error(`工具约束无效：${label}`);
      for (const clause of clauses) {
        if (!Array.isArray(clause) || !clause.length || !clause.every(v=>typeof v==='string'&&v.trim())) throw new Error(`工具约束无效：${label}`);
        for (const capability of clause) {
          const providers = [...tools.values()].filter(t => t.id === capability || t.provides.includes(capability));
          if (!providers.length) {
            if (!capability.startsWith('custom:')) throw new Error(`未定义工具能力：${capability}`);
            tools.set(capability, {id:capability,name:label,group:'其他工具',provides:[],note:'自定义菜谱新增；按原文核对。'});
            usedTools.add(capability);
          } else providers.forEach(t => usedTools.add(t.id));
        }
      }
      return {label, clauses};
    });
    const text = [recipe.title, recipe.taste, recipe.texture, recipe.technique, ...recipe.tags,
      ...ingredientIds.map(id => db.ingredients[id].name)].join(' ').toLocaleLowerCase();
    return {recipe, ingredientIds, requirements, text};
  });
  return {db, recipes, tools, usedTools, usedIngredients, categories};
}

export function sanitizeInventory(raw, index) {
  const value = raw && typeof raw === 'object' ? raw : {};
  const clean = (xs, allowed) => Array.isArray(xs) ? [...new Set(xs.filter(x => typeof x === 'string' && allowed.has(x)))] : [];
  return {
    version:1,
    ingredients:clean(value.ingredients, index.usedIngredients),
    tools:clean(value.tools, index.usedTools),
    categories:clean(value.categories, new Set(index.categories)),
  };
}

export function scopedEntries(index, categories = []) {
  const selected = new Set(categories);
  return selected.size ? index.recipes.filter(entry => selected.has(entry.recipe.category)) : index.recipes;
}

export function inventoryCandidates(index, categories = [], query = '') {
  const entries = scopedEntries(index, categories), ingredients = new Set(), capabilities = new Set();
  for (const entry of entries) {
    entry.ingredientIds.forEach(id => ingredients.add(id));
    entry.requirements.forEach(r => r.clauses.forEach(c => c.forEach(id => capabilities.add(id))));
  }
  const q = query.trim().toLocaleLowerCase();
  return {
    ingredients:[...ingredients].map(id => ({id, ...index.db.ingredients[id]})).filter(i => !q || `${i.name} ${i.group}`.toLocaleLowerCase().includes(q)),
    tools:[...index.tools.values()].filter(t => capabilities.has(t.id) || t.provides.some(id => capabilities.has(id)))
      .filter(t => !q || `${t.name} ${t.group} ${t.note}`.toLocaleLowerCase().includes(q)),
  };
}

export function matchInventory(index, inventory, options = {}) {
  const ingredients = new Set(inventory.ingredients), capabilities = new Set();
  for (const id of inventory.tools) {
    const tool = index.tools.get(id);
    if (tool) { capabilities.add(id); tool.provides.forEach(cap => capabilities.add(cap)); }
  }
  const q = (options.query ?? '').trim().toLocaleLowerCase();
  return scopedEntries(index, inventory.categories).filter(entry => !q || entry.text.includes(q)).map(entry => {
    const missingIngredients = entry.ingredientIds.filter(id => !ingredients.has(id));
    const missingTools = entry.requirements.filter(r => !r.clauses.every(clause => clause.some(id => capabilities.has(id)))).map(r => r.label);
    const needsFreezer = entry.recipe.needsFreezer && options.hasFreezer !== true;
    const ready = !missingIngredients.length && !missingTools.length && !needsFreezer;
    const status = ready ? 'ready' : missingTools.length || needsFreezer ? 'equipment' : 'ingredients';
    return {recipe:entry.recipe, missingIngredients, missingTools, needsFreezer, ready, status,
      missingCount:missingIngredients.length + missingTools.length + Number(needsFreezer)};
  });
}

export function searchEntries(index, {categories = [], query = '', experience = '全部', exclude = []} = {}) {
  const q = query.trim().toLocaleLowerCase(), excluded = new Set(exclude);
  return scopedEntries(index, categories).filter(e => (!q || e.text.includes(q)) &&
    (experience === '全部' || e.recipe.interaction === experience) && !excluded.has(e.recipe.id)).map(e => e.recipe);
}
