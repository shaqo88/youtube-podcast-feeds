(function(root) {
  'use strict';
  const keys={ follows:'torahpod:v1:follows',saved:'torahpod:v1:saved-episodes',
    progress:'torahpod-progress:',states:'torahpod:v1:episode-state',last:'torahpod-last-episode' };
  let engine=null;
  const owned=k=>k===keys.follows||k===keys.saved||k===keys.states||k===keys.last||k.startsWith(keys.progress);
  function guestGet(k) { try { return JSON.parse(localStorage.getItem(k)||'null'); } catch { return null; } }
  function guestSet(k,value) { try { localStorage.setItem(k,JSON.stringify(value)); } catch {} }
  function guestRemove(k) { try { localStorage.removeItem(k); } catch {} }
  function identity() { return engine?.identity||'guest'; }
  function get(k) { return engine && owned(k) ? engine.readLegacy(k) : guestGet(k); }
  function write(k,value,target=identity(),remove=false) {
    if (owned(k) && target!==identity()) return;
    if (engine && owned(k)) {
      engine.writeLegacy(k,value,remove).catch(()=>document.dispatchEvent(new CustomEvent('torahpod:storageerror')));
    } else if (remove) guestRemove(k); else guestSet(k,value);
  }
  function guestPreview() {
    const records=[];
    for (const [kind,key] of [['follows',keys.follows],['saved',keys.saved]]) {
      for (const value of guestGet(key)||[]) if (value?.slug||value?.id) records.push({kind,id:kind==='follows'?value.slug:value.id,value:{},metadata:value});
    }
    const progress=new Map();
    try {
      for (let i=0;i<localStorage.length;i++) {
        const key=localStorage.key(i); if (!key?.startsWith(keys.progress)) continue;
        const value=guestGet(key); if (!value || !Number.isFinite(value.position)) continue;
        progress.set(key.slice(keys.progress.length),{kind:'progress',id:key.slice(keys.progress.length),
          value:{position:value.position,duration:Number(value.duration)||0,completed:value.completed===true,
            recordedAt:Number.isSafeInteger(value.updatedAt)?value.updatedAt:null},metadata:value});
      }
    } catch {}
    for (const [id,state] of Object.entries(guestGet(keys.states)||{})) {
      const existing=progress.get(id);
      if (!existing || (Number.isSafeInteger(state.updatedAt) && state.updatedAt>(existing.value.recordedAt||0))) {
        progress.set(id,{kind:'progress',id,value:{position:existing?.value.position||0,duration:existing?.value.duration||0,
          completed:state.played===true,recordedAt:Number.isSafeInteger(state.updatedAt)?state.updatedAt:null},metadata:existing?.metadata||{id}});
      }
    }
    records.push(...progress.values());
    return records;
  }
  root.TorahPodStorage={ keys,get,set:write,remove:(k,target)=>write(k,null,target,true),identity,guestPreview,
    activate(value) { engine=value; document.dispatchEvent(new CustomEvent('torahpod:storagechange')); },
    forceProgress() { engine?.flush(true).catch(()=>{}); } };
  root.TorahPodStorage.beginPlayback=id=>engine?.beginPlayback(id).catch(()=>{});
  root.TorahPodStorage.progressHeld=id=>engine?.progressHeld(id)===true;
})(typeof window==='undefined'?globalThis:window);
