/** Room network boundary. Confirmed state is separate from optimistic, durable intentions. */
export const ROOM_POLICY = 'aggregate-public-v1';
const POINTER='campfire-room-pointer-v1', JOURNAL='campfire-room-op-v1:', ROOM_POINTER='campfire-room-entry-v1:';
export class RoomError extends Error {
  constructor(code, message, status = 0) { super(message); this.code=code; this.status=status; }
}
export function ownMember(room) { return room.members.find(m=>m.id===room.memberId); }
export function operationValue(room, op) {
  const mine=ownMember(room).choices;
  if (op.kind==='ingredient'||op.kind==='tool'||op.kind==='vote') return mine[{ingredient:'ingredients',tool:'tools',vote:'votes'}[op.kind]].includes(op.key);
  if (op.kind==='freezer') return mine.hasFreezer;
  if (op.kind==='portion') return room.settings.portions[op.key]??1;
  return room.settings[op.kind];
}
export function projectRoom(snapshot, pending) {
  if (!snapshot) return null;
  const room=structuredClone(snapshot), me=ownMember(room);
  for(const op of pending) {
    const field={ingredient:'ingredients',tool:'tools',vote:'votes'}[op.kind];
    if(field) {const ids=new Set(me.choices[field]);op.value?ids.add(op.key):ids.delete(op.key);me.choices[field]=[...ids];}
    else if(op.kind==='freezer') me.choices.hasFreezer=op.value;
    else if(op.kind==='portion') room.settings.portions[op.key]=op.value;
    else room.settings[op.kind]=structuredClone(op.value);
  }
  const selected=new Set(room.members.flatMap(m=>m.choices.votes));
  room.selected=[...room.settings.order.filter(id=>selected.has(id)),...Array.from(selected).filter(id=>!room.settings.order.includes(id)).sort()];
  room.inventory=Object.fromEntries(['ingredients','tools'].map(k=>[k,[...new Set(room.members.flatMap(m=>m.choices[k]))].sort()]));
  room.hasFreezer=room.members.some(m=>m.choices.hasFreezer);
  return room;
}
const validKey=value=>typeof value==='string'&&/^[A-Za-z][A-Za-z0-9-]{0,79}$/.test(value)&&!['constructor','prototype','__proto__'].includes(value);
export function validOperation(op) {
  if(!op||typeof op!=='object'||typeof op.id!=='string'||!/^[a-f0-9-]{32,36}$/.test(op.id))return false;
  if(Object.keys(op).some(k=>!['id','kind','key','value','expected'].includes(k)))return false;
  if(['ingredient','tool','vote'].includes(op.kind))return validKey(op.key)&&typeof op.value==='boolean'&&typeof op.expected==='boolean';
  if(op.kind==='freezer')return typeof op.value==='boolean'&&typeof op.expected==='boolean';
  if(op.kind==='people')return Number.isInteger(op.value)&&op.value>=1&&op.value<=16&&Number.isInteger(op.expected);
  if(op.kind==='portion')return validKey(op.key)&&[.25,.5,.75,1,1.5,2,3,4].includes(op.value)&&Number.isFinite(op.expected);
  if(op.kind==='order')return [op.value,op.expected].every(v=>Array.isArray(v)&&v.length<=50&&new Set(v).size===v.length&&v.every(validKey));
  return false;
}
export class RoomClient {
  constructor({onChange=()=>{},fetchImpl=globalThis.fetch.bind(globalThis),storage=null}={}) {
    Object.assign(this,{onChange,fetchImpl,storage,room:null,catalog:null,pending:[],blocked:false,status:'idle',message:'',active:false,flushing:false,retry:2000,storageOK:true});
    this.generation=0; this.timer=null; this.deadline=Infinity; this.restoreAttempted=false;
  }
  read(key) {try{return JSON.parse(this.storage?.getItem(key)||'null');}catch{return null;}}
  write(key,value) {try{if(!this.storage)throw new Error();value===null?this.storage.removeItem(key):this.storage.setItem(key,JSON.stringify(value));}catch{this.storageOK=false;}}
  emit() {this.onChange(this);}
  get view() {return projectRoom(this.room,this.pending);}
  journalKey(op,room=this.room) {return JOURNAL+room.id+':'+room.memberId+':'+op.id;}
  forgetPending(ops=this.pending,room=this.room) {if(room)for(const op of ops)this.write(this.journalKey(op,room),null);}
  forgetPointer(room=this.room) {
    if(!room)return;
    if(this.read(POINTER)?.id===room.id)this.write(POINTER,null);
    this.write(ROOM_POINTER+room.number,null);
  }
  clearJournal(room=this.room) {
    if(!room)return;
    const prefix=JOURNAL+room.id+':'+room.memberId+':',keys=[];
    try {for(let i=0;i<(this.storage?.length||0);i++){const key=this.storage.key(i);if(key?.startsWith(prefix))keys.push(key);}}
    catch {this.storageOK=false;}
    keys.forEach(key=>this.write(key,null));
  }
  persist() {
    if(!this.room)return;
    const pointer={id:this.room.id,number:this.room.number,expiresAt:this.room.expiresAt,memberId:this.room.memberId};
    this.write(POINTER,pointer);this.write(ROOM_POINTER+this.room.number,pointer);
    for(const op of this.pending) {
      const key=this.journalKey(op),prior=this.read(key);
      this.write(key,{roomId:this.room.id,memberId:this.room.memberId,expiresAt:this.room.expiresAt,
        created:prior?.created??performance.timeOrigin+performance.now(),operation:op,blocked:this.blocked});
    }
  }
  restorePending(snapshot) {
    const rows=[],prefix=JOURNAL+snapshot.id+':'+snapshot.memberId+':';
    try {for(let i=0;i<(this.storage?.length||0);i++){const key=this.storage.key(i);if(!key?.startsWith(prefix))continue;
      const r=this.read(key);if(r?.roomId===snapshot.id&&r.memberId===snapshot.memberId&&r.expiresAt===snapshot.expiresAt&&validOperation(r.operation)&&Number.isFinite(r.created))rows.push(r);
    }}catch{this.storageOK=false;}
    rows.sort((a,b)=>a.created-b.created||a.operation.id.localeCompare(b.operation.id));
    this.pending=rows.slice(0,500).map(r=>r.operation);this.blocked=rows.some(r=>r.blocked===true);
  }
  async request(path,method='GET',value) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
    try {
      const response=await this.fetchImpl('/api/rooms'+path,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,
        headers:{'X-Room-Client':'1',...(value!==undefined?{'Content-Type':'application/json'}:{})},...(value!==undefined?{body:JSON.stringify(value)}:{})});
      let data;try{data=await response.json();}catch{throw new RoomError('SERVICE_UNAVAILABLE','房间服务尚未就绪，个人菜单仍可离线使用。',response.status);}
      if(!response.ok)throw new RoomError(data.error?.code||'SERVER_ERROR',data.error?.message||'房间服务暂时不可用。',response.status);
      return data;
    } catch(error) {if(error instanceof RoomError)throw error;throw new RoomError('NETWORK','连接中断，未确认的操作会保留并重试。');}
    finally {clearTimeout(timer);}
  }
  accept(snapshot) {
    // Server time + monotonic elapsed time: changing the device wall clock cannot extend this visit.
    this.deadline=performance.now()+Math.max(0,(snapshot.expiresAt-snapshot.serverTime)*1000);
    if(!snapshot.unchanged && (!this.room||snapshot.revision>=this.room.revision))this.room=snapshot;
    this.retry=2000;
  }
  async enter(mode,fields) {
    const generation=++this.generation;
    clearTimeout(this.timer);this.status='joining';this.message='正在连接房间…';this.emit();
    try {
      await this.request('/session','POST',{});
      const snapshot=await this.request(mode==='create'?'':'/join','POST',{...fields,archivePolicy:ROOM_POLICY});
      const catalog=await this.request('/'+snapshot.id+'/catalog');
      if(generation!==this.generation)return;
      this.room=null;this.accept(snapshot);this.catalog=catalog;this.restorePending(snapshot);
      this.persist();this.status=this.blocked?'conflict':this.pending.length?'saving':'synced';this.message='';this.emit();this.flush();this.schedule();
    }catch(error){if(generation!==this.generation)return;this.status='error';this.message=error.message;this.emit();throw error;}
  }
  async resume(number='') {
    if(this.restoreAttempted||this.room)return;
    this.restoreAttempted=true;
    const pointer=number?this.read(ROOM_POINTER+number)||this.read(POINTER):this.read(POINTER);
    if(!pointer||!(/^[a-f0-9]{32}$/).test(pointer.id)||number&&number!==pointer.number)return;
    if(!Number.isFinite(pointer.expiresAt)||Date.now()/1000>=pointer.expiresAt){this.clearJournal(pointer);this.forgetPointer(pointer);this.closeExpired();return;}
    const generation=++this.generation;
    this.status='joining';this.message='正在恢复房间…';this.emit();
    try {
      const snapshot=await this.request('/'+pointer.id);
      const catalog=await this.request('/'+pointer.id+'/catalog');
      if(generation!==this.generation)return;
      this.accept(snapshot);this.catalog=catalog;
      this.restorePending(snapshot);
      this.status=this.blocked?'conflict':this.pending.length?'saving':'synced';
      this.message=this.blocked?'另一个页面修改过同一项，请核对待同步选择。':'';
      this.emit();this.persist();this.flush();this.schedule();
    }catch(error){if(generation!==this.generation)return;if([401,403,404].includes(error.status)){this.clearJournal(pointer);this.forgetPointer(pointer);this.closeExpired('房间已到期或浏览器身份已失效，请重新加入。');}else{this.status='error';this.message=error.message;this.restoreAttempted=false;this.emit();}}
  }
  setActive(active) {this.active=active;clearTimeout(this.timer);if(active){if(this.room)this.schedule(0);}}
  schedule(delay=this.retry) {
    clearTimeout(this.timer);
    if(this.active&&this.room)this.timer=setTimeout(()=>this.tick(),Math.min(delay,Math.max(0,this.deadline-performance.now())));
  }
  closeExpired(message='房间已到期，无法继续进入。菜单与物资汇总将由服务器归档。') {
    this.generation++;clearTimeout(this.timer);this.clearJournal();this.forgetPointer();this.room=null;this.catalog=null;this.pending=[];this.blocked=false;
    this.status='closed';this.message=message;this.emit();
  }
  async tick() {
    if(!this.room)return;
    if(performance.now()>=this.deadline){this.closeExpired();return;}
    if(this.flushing){this.schedule();return;}
    if(this.pending.length&&!this.blocked){await this.flush();this.schedule();return;}
    const generation=this.generation;
    try {
      const snapshot=await this.request('/'+this.room.id+'?after='+this.room.revision);
      if(generation!==this.generation)return;
      this.accept(snapshot);this.status=this.blocked?'conflict':'synced';
      if(!this.blocked)this.message='';
      if(!snapshot.unchanged)this.persist();
      this.emit();
    }catch(error){if(generation!==this.generation)return;if([401,403,404].includes(error.status)){this.closeExpired();return;}this.status='offline';this.message=error.message;this.retry=Math.min(30000,this.retry*2);this.emit();}
    this.schedule();
  }
  enqueue(kind,key,value) {
    if(!this.room||performance.now()>=this.deadline){this.closeExpired();return;}
    if(this.blocked)throw new RoomError('CONFLICT','请先核对并处理未同步的选择。');
    if(this.pending.length>=500)throw new RoomError('QUEUE_FULL','待同步操作较多，请连接网络后继续。');
    const op={id:crypto.randomUUID(),kind,...(key!==undefined?{key}:{}),value};
    op.expected=structuredClone(operationValue(this.view,op));
    if(!validOperation(op))throw new RoomError('INVALID_INPUT','请选择有效的物资、份量或人数。');
    if(JSON.stringify(value)===JSON.stringify(op.expected))return;
    this.pending.push(op);this.status='saving';this.message='';this.persist();this.emit();this.flush();
  }
  async flush() {
    if(this.flushing||this.blocked||!this.room||!this.pending.length)return;
    this.flushing=true;const generation=this.generation;
    try {
      while(this.pending.length&&!this.blocked&&this.room&&generation===this.generation) {
        if(performance.now()>=this.deadline){this.closeExpired();return;}
        const op=this.pending[0];
        try {
          const snapshot=await this.request('/'+this.room.id+'/ops','POST',op);
          if(generation!==this.generation)return;
          if(snapshot.appliedId!==op.id)throw new RoomError('ACK_INVALID','保存回执不匹配，保留操作等待重试。');
          this.write(this.journalKey(op),null);this.pending.shift();this.accept(snapshot);this.status=this.pending.length?'saving':'synced';this.message='';this.persist();this.emit();
        }catch(error){
          if(generation!==this.generation)return;
          if(error.code==='ROOM_UNAVAILABLE'||[401,403].includes(error.status)){this.closeExpired(error.message);return;}
          if(error.status>=400&&error.status<500&&error.status!==429){
            this.blocked=true;this.status='conflict';this.message=error.message;
            try{this.accept(await this.request('/'+this.room.id));}catch{}
          }else{this.status='offline';this.message=error.message;this.retry=Math.min(30000,this.retry*2);}
          this.persist();this.emit();break;
        }
      }
    }finally{this.flushing=false;this.schedule();}
  }
  async resolve(keepMine) {
    if(!this.room||this.flushing)return;
    const generation=this.generation;
    const snapshot=await this.request('/'+this.room.id);
    if(generation!==this.generation)return;
    this.accept(snapshot);
    const queued=keepMine?this.pending:[];this.forgetPending();this.pending=[];this.blocked=false;
    for(const op of queued){op.id=crypto.randomUUID();op.expected=structuredClone(operationValue(this.view,op));this.pending.push(op);}
    this.status=this.pending.length?'saving':'synced';this.message='';this.persist();this.emit();this.flush();
  }
  leave() {
    this.generation++;clearTimeout(this.timer);this.forgetPending();this.forgetPointer();this.room=null;this.catalog=null;this.pending=[];this.blocked=false;
    this.status='idle';this.message='已退出。你已经同步的选择仍留在房间里。';this.emit();
  }
}
