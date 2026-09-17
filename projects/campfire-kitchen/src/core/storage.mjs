/** No globals in storage adapter: failures remain visible and corrupt input is preserved. */
export function readJSONStorage(storage, key) {
  try {
    const raw = storage.getItem(key);
    if (raw === null) return {ok:true,value:null,raw:null};
    try { return {ok:true,value:JSON.parse(raw),raw}; }
    catch { return {ok:false,value:null,raw,error:'保存的数据不是有效JSON'}; }
  } catch { return {ok:false,value:null,raw:null,error:'浏览器不允许读取本地存储'}; }
}
export function writeJSONStorage(storage, key, value) {
  try { storage.setItem(key,JSON.stringify(value)); return true; }
  catch { return false; }
}
