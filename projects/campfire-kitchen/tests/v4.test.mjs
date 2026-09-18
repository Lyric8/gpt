import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { loadCatalog } from '../tools/load_catalog.mjs';
import { paginate, PAGE_SIZE } from '../src/core/pagination.mjs';
import { makeInventoryIndex, sanitizeInventory, matchInventory, searchEntries } from '../src/core/pantry.mjs';
import { sanitizeState } from '../src/engine.mjs';
const db=loadCatalog();
const equipment=JSON.parse(fs.readFileSync(new URL('../data/equipment.json',import.meta.url)));
const index=makeInventoryIndex(db,equipment);
const full={version:1,categories:[],ingredients:[...index.usedIngredients],tools:[...index.usedTools]};
test('300 unique dishes, 25 smoke dishes, every builtin equipment requirement resolves explicitly',()=>{
 assert.equal(db.recipes.length,300);assert.equal(new Set(db.recipes.map(r=>r.title)).size,300);
 assert.equal(db.recipes.filter(r=>r.category==='苹果木烟熏').length,25);
 for(const r of db.recipes)for(const label of r.equipment)assert.ok(equipment.requirements[label],`${r.id}: ${label}`);
 assert.equal(matchInventory(index,full,{hasFreezer:true}).filter(m=>m.ready).length,300);
});
test('pagination reaches every dish exactly once with bounded DOM pages',()=>{
 const ids=[];for(let page=1;page<=13;page++){const view=paginate(db.recipes,page);assert.ok(view.items.length<=PAGE_SIZE);ids.push(...view.items.map(r=>r.id));}
 assert.equal(ids.length,300);assert.equal(new Set(ids).size,300);assert.equal(paginate(db.recipes,99).page,13);
 assert.equal(paginate([],NaN).first,0);assert.equal(paginate(db.recipes,-1).page,1);
 assert.throws(()=>paginate([],1,0),TypeError);
});
test('applewood does not replace charcoal, open grill does not replace covered grill',()=>{
 for(const missing of ['apple-wood','probe','grill-thermometer','covered-grill']){
  const inv={...full,tools:full.tools.filter(id=>id!==missing)};
  const smoke=matchInventory(index,inv,{hasFreezer:true}).filter(m=>m.recipe.category==='苹果木烟熏');
  assert.equal(smoke.filter(m=>m.ready).length,0,missing);
 }
 const withoutFuel={...full,tools:full.tools.filter(id=>!['bbq-charcoal','bamboo-charcoal'].includes(id))};
 assert.ok(matchInventory(index,withoutFuel,{hasFreezer:true}).filter(m=>m.recipe.category==='苹果木烟熏').every(m=>!m.ready));
 const bambooOnly={...full,tools:full.tools.filter(id=>id!=='bbq-charcoal')};
 assert.ok(matchInventory(index,bambooOnly,{hasFreezer:true}).filter(m=>m.recipe.category==='苹果木烟熏').every(m=>m.ready));
});
test('empty stock does not infer user ownership or salt/oil',()=>{
 const inv=sanitizeInventory(null,index);assert.equal(inv.ingredients.length,0);assert.equal(inv.tools.length,0);
 assert.equal(matchInventory(index,inv,{hasFreezer:false}).filter(m=>m.ready).length,0);
});
test('search exposes cooking modes and durations are finite for every dish',()=>{
 assert.equal(searchEntries(index,{query:'苹果木'}).length,25);
 for(const r of db.recipes){assert.ok(Number.isFinite(r.totalMinutes));assert.ok(r.completion.length>10);assert.ok(r.serving.length>10);assert.ok(r.fireSetup.length>10);}
});
test('obsolete countdown is cleared during persisted-state migration and absent from app',()=>{
 assert.equal(sanitizeState({timer:{endsAt:Date.now()+60000,label:'旧提醒'}},db).timer,null);
 for(const path of ['src/app.mjs','src/ui/recipe.mjs']){
  const text=fs.readFileSync(new URL('../'+path,import.meta.url),'utf8');assert.ok(!text.includes('setInterval'));assert.ok(!text.includes('data-action="timer"'));assert.ok(!text.includes('updateTimer'));
 }
});
