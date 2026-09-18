import { RoomClient, ownMember } from './client.mjs';
import { lobbyView, workspaceView, roomRecipeHTML, roomPlan } from './view.mjs';
import { makeInventoryIndex } from '../core/pantry.mjs';
import { validateDatabase, defaultState, makeMarkdown } from '../engine.mjs';
export function createRoomsUI({photos,readPersonal}) {
  let storage=null;try{storage=localStorage;}catch{}
  const state={element:null,photos,mode:'create',fields:{},scope:[],query:'',supplyQuery:'',supplyKind:'ingredients',
    readyOnly:false,page:1,pane:'dishes',note:'',shareOpen:false,index:null,db:null};
  const expanded=new Map();let catalogObject=null,signature='',recipeId=null,recipeTrigger='',dialog=null;
  const client=new RoomClient({storage,onChange:()=>render()});state.client=client;
  function ctx() {
    if(client.catalog!==catalogObject&&client.catalog) {
      const validation=validateDatabase(client.catalog.database);
      if(!validation.ok)throw new Error('房间菜谱校验失败，请联系房主更新服务。');
      state.db=client.catalog.database;state.index=makeInventoryIndex(state.db,client.catalog.equipment);catalogObject=client.catalog;
    }
    return {...state,room:client.view};
  }
  function focusKey(el) {
    if(!el||el===document.body)return '';
    if(el.id)return '#'+CSS.escape(el.id);
    return ['data-room-action','data-room-kind','data-room-portion','data-id','data-value','data-delta'].filter(k=>el.hasAttribute(k)).map(k=>`[${k}="${CSS.escape(el.getAttribute(k))}"]`).join('');
  }
  function render(force=false) {
    if(!state.element)return;
    const key=JSON.stringify([client.room?.revision,client.room?.id,client.status,client.pending,client.blocked,client.message,client.storageOK]);
    if(!force&&signature===key)return;signature=key;
    const active=document.activeElement,focus=state.element.contains(active)?focusKey(active):'';
    const selection=active?.selectionStart,scroll=window.scrollY;
    state.element.querySelectorAll('details[data-room-keep]').forEach(d=>expanded.set(d.dataset.roomKeep,d.open));
    try {state.element.innerHTML=client.room&&client.catalog?workspaceView(ctx()):lobbyView(state);}
    catch(error){state.element.textContent=error.message;return;}
    state.element.querySelectorAll('details[data-room-keep]').forEach(d=>{if(expanded.has(d.dataset.roomKeep)&&!state.supplyQuery)d.open=expanded.get(d.dataset.roomKeep);});
    if(focus){const target=state.element.querySelector(focus);target?.focus({preventScroll:true});if(target&&Number.isInteger(selection))try{target.setSelectionRange(selection,selection);}catch{}}
    window.scrollTo(0,scroll);
    if(recipeId&&dialog?.open){if(!client.room){closeRecipe();}else updateRecipe();}
  }
  function note(message){state.note=message;render(true);}
  function ensureDialog() {
    if(dialog)return;
    dialog=document.createElement('dialog');dialog.id='room-recipe-dialog';dialog.setAttribute('aria-labelledby','room-recipe-title');
    document.body.append(dialog);dialog.addEventListener('click',action);
    dialog.addEventListener('close',()=>{recipeId=null;if(recipeTrigger)state.element?.querySelector(recipeTrigger)?.focus({preventScroll:true});});
    dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeRecipe();}});
  }
  function updateRecipe() {
    const old=dialog.querySelector('.dialog-body')?.scrollTop||0,focus=dialog.contains(document.activeElement)?focusKey(document.activeElement):'';
    dialog.innerHTML=roomRecipeHTML(ctx(),recipeId);dialog.querySelector('.dialog-body').scrollTop=old;
    if(focus)dialog.querySelector(focus)?.focus({preventScroll:true});
  }
  function closeRecipe(){if(dialog?.open)dialog.close();recipeId=null;}
  function openRecipe(id){ensureDialog();recipeId=id;recipeTrigger=focusKey(document.activeElement);updateRecipe();dialog.querySelector('.dialog-body').scrollTop=0;if(!dialog.open)dialog.showModal();}
  function download(text,name) {
    const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;
    document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }
  async function action(event) {
    const button=event.target.closest('[data-room-action]');if(!button)return;
    event.preventDefault();const {roomAction:a,id,value}=button.dataset;
    try {
      if(a==='resume'){await client.resume(state.fields.number||'');}
      else if(a==='mode'){state.mode=value;state.fields.passcode='';client.message='';render(true);}
      else if(a==='pane'){state.pane=value;state.note='';render(true);}
      else if(a==='scope'){state.scope=!id?[]:state.scope.includes(id)?state.scope.filter(x=>x!==id):[...state.scope,id];state.page=1;render(true);}
      else if(a==='supply-kind'){state.supplyKind=value;render(true);}
      else if(a==='page'){state.page=Number(button.dataset.page);render(true);state.element.querySelector('.room-result-count')?.scrollIntoView({block:'start'});}
      else if(a==='vote'){const mine=ownMember(client.view).choices.votes.includes(id);client.enqueue('vote',id,!mine);}
      else if(a==='detail')openRecipe(id);
      else if(a==='close-recipe')closeRecipe();
      else if(a==='share'){state.shareOpen=!state.shareOpen;render(true);if(state.shareOpen)state.element.querySelector('#room-share-link')?.focus();}
      else if(a==='copy'){
        const link=location.origin+location.pathname+'#rooms/'+client.room.number;
        try{await navigator.clipboard.writeText(`来火边一起点菜，房号 ${client.room.number}\n${link}\n${client.room.locked?'口令向房主索取。':'知道房号即可加入。'}`);note('邀请已复制。');}
        catch{const input=state.element.querySelector('#room-share-link');input?.focus();input?.select();note('浏览器不允许自动复制，请复制已选中的链接。');}
      }
      else if(a==='move'){
        const order=[...client.view.selected],i=order.indexOf(id),to=i+Number(button.dataset.delta);
        if(i>=0&&to>=0&&to<order.length){[order[i],order[to]]=[order[to],order[i]];client.enqueue('order',undefined,order);}
      }
      else if(a==='import-own'){
        const personal=readPersonal(),pending=[];const mine=ownMember(client.view).choices;
        for(const [field,kind,allowed] of [['ingredients','ingredient',state.index.usedIngredients],['tools','tool',state.index.usedTools]])
          for(const key of personal[field]||[])if(allowed.has(key)&&!mine[field].includes(key))pending.push([kind,key,true]);
        if(!pending.length){note('个人库存中没有需要带入的新物资。');return;}
        if(confirm(`把本机库存中的 ${pending.length} 项带入为“我能带”？不导入私人笔记、菜单或备料进度。`)){
          if(client.pending.length+pending.length>500){note('待同步操作太多，请先等当前选择同步完成。');return;}
          pending.forEach(args=>client.enqueue(...args));note('已带入，正在与房间同步。');
        }
      }
      else if(a==='resolve-mine'){if(confirm('已核对页面了吗？以你当前显示的待同步选择重新提交；不会改变别人的认领。'))await client.resolve(true);}
      else if(a==='resolve-server'){if(confirm('放弃本机尚未确认的修改，保留服务器已经保存的选择？'))await client.resolve(false);}
      else if(a==='leave'){
        if(client.flushing){note('正在确认刚才的保存，请在结果返回后退出。');return;}
        if(client.pending.length&&!confirm('还有未确认的操作。退出会丢弃本机待同步记录；已经发出的请求仍可能已提交。继续退出？'))return;
        closeRecipe();client.leave();state.fields={};state.shareOpen=false;history.replaceState(null,'','#rooms');render(true);
      }
      else if(a==='export'){
        if(client.pending.length||client.status!=='synced'){note('请先确认所有选择已同步，再导出这桌清单。');return;}
        const room=client.room;
        download(makeMarkdown(state.db,{...defaultState(),people:room.settings.people,selected:room.selected,portions:room.settings.portions,order:room.selected,hasFreezer:room.hasFreezer,menuName:`房间 ${room.number} · 这桌菜单`}),`火边房间-${room.number}-菜单.md`);
      }
    }catch(error){note(error.message);}
  }
  function input(event) {
    const t=event.target;
    if(t.closest('#room-entry-form')&&t.name)state.fields[t.name]=t.value;
    if(t.id==='room-dish-search'){state.query=t.value;state.page=1;render(true);}
    if(t.id==='room-supply-search'){state.supplyQuery=t.value;render(true);}
  }
  function change(event) {
    const t=event.target;try {
      if(t.dataset.roomKind)client.enqueue(t.dataset.roomKind,t.dataset.id,t.checked);
      else if(t.id==='room-freezer')client.enqueue('freezer',undefined,t.checked);
      else if(t.id==='room-people'){if(!t.checkValidity()||!Number.isInteger(Number(t.value))){note('用餐人数请输入1—16的整数。');return;}client.enqueue('people',undefined,Number(t.value));}
      else if(t.dataset.roomPortion)client.enqueue('portion',t.dataset.roomPortion,Number(t.value));
      else if(t.id==='room-ready-only'){state.readyOnly=t.checked;state.page=1;render(true);}
    }catch(error){note(error.message);}
  }
  async function submit(event) {
    if(event.target.id!=='room-entry-form')return;event.preventDefault();
    if(client.status==='joining')return;
    state.fields=Object.fromEntries(new FormData(event.target));
    try {await client.enter(state.mode,state.fields);state.fields.passcode='';state.pane='dishes';history.replaceState(null,'','#rooms/'+client.room.number);render(true);}
    catch{}
  }
  function route() {
    const requested=/^#rooms\/([0-9]{4,12})$/.exec(location.hash)?.[1]||'';
    if(client.room&&requested&&requested!==client.room.number) {
      if(client.flushing||(client.pending.length&&!confirm('切换房间会放弃本页未确认的修改。已经发出的请求仍可能已保存，继续？'))) {
        history.replaceState(null,'','#rooms/'+client.room.number);note('请先确认当前房间的保存结果。');return;
      }
      closeRecipe();client.leave();client.restoreAttempted=false;state.fields={};state.scope=[];state.query='';state.shareOpen=false;
    }
    if(!client.room&&requested){state.mode='join';state.fields.number=requested;}
    render(true);if(location.protocol!=='file:')client.resume(requested);
  }
  function mount(element) {
    if(state.element===element)return;
    if(state.element){state.element.removeEventListener('click',action);state.element.removeEventListener('input',input);state.element.removeEventListener('change',change);state.element.removeEventListener('submit',submit);}
    state.element=element;signature='';client.setActive(Boolean(element)&&!document.hidden);
    if(!element){closeRecipe();return;}
    element.addEventListener('click',action);element.addEventListener('input',input);element.addEventListener('change',change);element.addEventListener('submit',submit);
    route();
  }
  document.addEventListener('visibilitychange',()=>client.setActive(Boolean(state.element)&&!document.hidden));
  window.addEventListener('online',()=>{if(state.element){if(client.room)client.schedule(0);else client.resume(state.fields.number||'');}});
  window.addEventListener('pagehide',()=>client.persist());
  return Object.freeze({mount,route});
}
