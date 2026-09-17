import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { makeInventoryIndex, sanitizeInventory, scopedEntries, inventoryCandidates, matchInventory, searchEntries } from '../src/core/pantry.mjs';
import { suggestMeals } from '../src/core/recommendations.mjs';
import { defaultState, recipeView } from '../src/engine.mjs';
import { readJSONStorage, writeJSONStorage } from '../src/core/storage.mjs';
const db=JSON.parse(readFileSync(new URL('../data/recipes.json',import.meta.url)));
const equipment=JSON.parse(readFileSync(new URL('../data/equipment.json',import.meta.url)));
const index=makeInventoryIndex(db,equipment);
const empty=()=>sanitizeInventory(null,index);
const all=()=>sanitizeInventory({ingredients:[...index.usedIngredients],tools:[...index.usedTools]},index);
const byId=(results,id)=>results.find(m=>m.recipe.id===id);

test('canonical inventory is complete, scoped and deduplicated',()=>{
 assert.equal(index.recipes.length,50);assert.equal(index.categories.length,6);
 const cleaned=sanitizeInventory({ingredients:['salt','salt','bad',4],tools:['tongs','tongs','bad'],categories:['肉类','bad','肉类']},index);
 assert.deepEqual(cleaned.ingredients,['salt']);assert.deepEqual(cleaned.tools,['tongs']);assert.deepEqual(cleaned.categories,['肉类']);
 assert.equal(inventoryCandidates(index).ingredients.length,index.usedIngredients.size);
 assert.equal(inventoryCandidates(index).tools.length,index.usedTools.size);
});
test('zero inventory never implies oil, salt, sauce or a pot',()=>{
 const matches=matchInventory(index,empty());assert.equal(matches.filter(m=>m.ready).length,0);
 assert(matches.every(m=>m.missingIngredients.length>0));
});
test('full inventory supports every recipe only when freezer is confirmed',()=>{
 const matches=matchInventory(index,all(),{hasFreezer:true});assert.equal(matches.filter(m=>m.ready).length,50);
 const noFreezer=matchInventory(index,all());assert.equal(noFreezer.filter(m=>!m.ready).length,db.recipes.filter(r=>r.needsFreezer).length);
 assert(noFreezer.filter(m=>!m.ready).every(m=>m.needsFreezer&&m.status==='equipment'));
});
for(const category of index.categories){
 test(`scope derives candidate union from recipes only: ${category}`,()=>{
  const entries=scopedEntries(index,[category]);assert(entries.length>0);
  const candidates=inventoryCandidates(index,[category]);
  assert.deepEqual(new Set(candidates.ingredients.map(i=>i.id)),new Set(entries.flatMap(e=>e.ingredientIds)));
  const wantedCaps=new Set(entries.flatMap(e=>e.requirements.flatMap(r=>r.clauses.flat())));
  assert(candidates.tools.every(t=>wantedCaps.has(t.id)||t.provides.some(c=>wantedCaps.has(c))));
  const owned={...all(),categories:[category]};assert.equal(matchInventory(index,owned,{hasFreezer:true}).length,entries.length);
 });
}
test('multi category is OR scope and changing it preserves inventory',()=>{
 const owned=all();const before=JSON.stringify(owned);
 const a=scopedEntries(index,['肉类']),b=scopedEntries(index,['蔬菜']);
 assert.equal(scopedEntries(index,['肉类','蔬菜']).length,a.length+b.length);
 inventoryCandidates(index,['肉类']);matchInventory(index,{...owned,categories:['蔬菜']});
 assert.equal(JSON.stringify(owned),before);
});
test('candidate search never introduces global out-of-scope items',()=>{
 const scoped=inventoryCandidates(index,['甜品与饮料']);const search=inventoryCandidates(index,['甜品与饮料'],'牛肉');
 assert.equal(search.ingredients.length,0);
 assert(inventoryCandidates(index,['肉类'],'牛肉').ingredients.every(i=>i.name.includes('牛肉')));
 assert.equal(inventoryCandidates(index,['甜品与饮料'],' \n ').ingredients.length,scoped.ingredients.length);
});
for(const entry of index.recipes){
 test(`all prerequisites individually enforced: ${entry.recipe.id}`,()=>{
  const owned=all();const match=byId(matchInventory(index,owned,{hasFreezer:true}),entry.recipe.id);
  assert.equal(match.ready,true);
  const missing=entry.ingredientIds[0];owned.ingredients=owned.ingredients.filter(id=>id!==missing);
  const denied=byId(matchInventory(index,owned,{hasFreezer:true}),entry.recipe.id);
  assert.equal(denied.ready,false);assert.deepEqual(denied.missingIngredients,[missing]);assert.equal(denied.status,'ingredients');
 });
}
function toolRecipe(labels,owned){
 const d={...db,recipes:[{...db.recipes[0],equipment:labels}]};const idx=makeInventoryIndex(d,equipment);
 return matchInventory(idx,sanitizeInventory({ingredients:db.recipes[0].ingredients.map(i=>i.ingredient),tools:owned},idx))[0];
}
test('OR tools accept either implement, not both mandatory',()=>{
 assert(toolRecipe(['夹子/铲子'],['spatula']).ready);assert(toolRecipe(['夹子/铲子'],['tongs']).ready);
 assert(!toolRecipe(['夹子/铲子'],['spoon']).ready);
});
test('raw and cooked two-tool requirement is AND, never one shared tong',()=>{
 assert(!toolRecipe(['生熟分开的夹子'],['tongs']).ready);
 assert(!toolRecipe(['生熟两夹'],['raw-tongs']).ready);
 assert(toolRecipe(['生熟两夹'],['raw-tongs','tongs']).ready);
 assert(toolRecipe(['生熟分开的夹子'],['tongs-pair']).ready);
});
test('stronger exact cookware capability is allowed, weaker cookware rejected',()=>{
 assert(toolRecipe(['带沿小锅'],['thick-pot15']).ready);
 assert(!toolRecipe(['至少1.5L带盖厚底小锅'],['pot']).ready);
 assert(!toolRecipe(['适配锅盖'],['lidded-pot']).ready);
 assert(!toolRecipe(['两只小餐杯'],['cup']).ready);
 assert(toolRecipe(['两只小餐杯'],['cup-pair']).ready);
});
test('unknown custom recipe tools become explicit exact candidates',()=>{
 const d={...db,recipes:[{...db.recipes[0],equipment:['专用锅 A']}]};const idx=makeInventoryIndex(d,equipment);
 assert.equal(inventoryCandidates(idx).tools[0].id,'custom:专用锅 A');
 const inv=sanitizeInventory({ingredients:[...idx.usedIngredients]},idx);assert.equal(matchInventory(idx,inv)[0].ready,false);
 inv.tools=['custom:专用锅 A'];assert.equal(matchInventory(idx,inv)[0].ready,true);
});
test('search and history exclusion use the same recipe-derived vocabulary',()=>{
 assert.deepEqual(searchEntries(index,{query:'米纸'}).map(r=>r.id),['summer-roll']);
 assert(!searchEntries(index,{exclude:['summer-roll']}).some(r=>r.id==='summer-roll'));
 assert(searchEntries(index,{categories:['主食'],experience:'动手'}).every(r=>r.category==='主食'&&r.interaction==='动手'));
});
test('recommendations cannot use missing ingredients, tools or freezer',()=>{
 const inv=all();inv.ingredients=inv.ingredients.filter(id=>id!=='beef');inv.tools=[];
 const matches=matchInventory(index,inv);const allowed=new Set(matches.filter(m=>m.ready).map(m=>m.recipe.id));
 const meals=suggestMeals(db,matches,defaultState());assert(meals.every(m=>m.recipes.every(r=>allowed.has(r.id))));
});
test('recommendations are deterministic, unique and respect operation budgets',()=>{
 const matches=matchInventory(index,all(),{hasFreezer:true});const state=defaultState();state.hasFreezer=true;
 const meals=suggestMeals(db,matches,state);assert(meals.length>=2&&meals.length<=3);
 assert.deepEqual(meals,suggestMeals(db,matches,state));
 const signatures=meals.map(m=>m.recipes.map(r=>r.id).sort().join(','));assert.equal(new Set(signatures).size,signatures.length);
 for(const m of meals){assert(m.recipes.length>=2&&m.recipes.length<=(m.id==='quick'?3:4));assert(m.active<=(m.id==='quick'?35:65));
  assert.equal(new Set(m.recipes.map(r=>r.main)).size,m.recipes.length);assert(m.reasons.length>=2);assert(m.note.includes('合计用量'));
 }
});
test('recommendation estimate uses actual people and resets recommended portions to one',()=>{
 const matches=matchInventory(index,all(),{hasFreezer:true});const state={...defaultState(),people:4,portions:Object.fromEntries(db.recipes.map(r=>[r.id,.25]))};
 for(const meal of suggestMeals(db,matches,state)){
  assert.equal(meal.active,Math.ceil(meal.recipes.reduce((sum,r)=>sum+recipeView(db,r.id,state,1).activeEstimate,0)));
  assert(meal.recipes.every(r=>r.portion===1));
 }
});
test('zero or one feasible recipe cannot become a fictitious meal combination',()=>{
 assert.deepEqual(suggestMeals(db,[],defaultState()),[]);
 assert.deepEqual(suggestMeals(db,[{recipe:db.recipes[0],ready:true}],defaultState()),[]);
});
test('storage preserves corrupt raw bytes and reports denied/quota failures',()=>{
 const store=new Map([['bad','{bad']]);const storage={getItem:k=>store.get(k)??null,setItem:(k,v)=>store.set(k,v)};
 assert.equal(readJSONStorage(storage,'missing').value,null);assert.equal(readJSONStorage(storage,'bad').raw,'{bad');
 assert.equal(readJSONStorage(storage,'bad').ok,false);assert.equal(store.get('bad'),'{bad');
 assert(writeJSONStorage(storage,'ok',{x:1}));assert.deepEqual(readJSONStorage(storage,'ok').value,{x:1});
 const denied={getItem(){throw Error('denied')},setItem(){throw Error('quota')}};
 assert.equal(readJSONStorage(denied,'a').ok,false);assert.equal(writeJSONStorage(denied,'a',{}),false);
});

test('malformed tool catalog fails closed before availability can be claimed',()=>{
  const valid=JSON.parse(readFileSync(new URL('../data/equipment.json',import.meta.url)));
  for (const mutate of [
    x=>x.schemaVersion=9,
    x=>x.tools.push({...x.tools[0]}),
    x=>x.tools[0].provides=null,
    x=>x.requirements[db.recipes[0].equipment[0]]=[],
    x=>x.requirements[db.recipes[0].equipment[0]]=[[]],
    x=>x.requirements[db.recipes[0].equipment[0]]=[[42]],
  ]) {const bad=structuredClone(valid);mutate(bad);assert.throws(()=>makeInventoryIndex(db,bad));}
});
