const clone=value=>structuredClone(value);
const keyOf=(kind,id)=>`${kind}:${id}`;
const blank=()=>({ records:{},outbox:[],conflicts:{},metadata:{},resumeSelections:{},cursor:0,importChoice:null,importJob:null,last:null });
export function openStore(environment,indexedDB=globalThis.indexedDB) {
  return new Promise((resolve,reject)=>{
    const request=indexedDB.open(`torahpod-accounts-${environment}`,1);
    request.onupgradeneeded=()=>request.result.createObjectStore('sessions');
    request.onerror=()=>reject(request.error);
    request.onsuccess=()=>resolve(request.result);
  });
}
export function transact(db,uid,change) {
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('sessions','readwrite'),store=tx.objectStore('sessions');
    let result;
    const request=store.get(uid);
    request.onsuccess=()=>{
      try { result=change(request.result||blank()); if (result===null) store.delete(uid); else store.put(result,uid); }
      catch(error) { reject(error);tx.abort(); }
    };
    tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||new Error('storage_unavailable'));
  });
}
function progress(value) {
  return {position:Math.min(86400,Math.max(0,Number(value.position)||0)),duration:Math.min(86400,Math.max(0,Number(value.duration)||0)),
    completed:value.completed===true,recordedAt:Number.isSafeInteger(value.updatedAt)?value.updatedAt:Date.now()};
}
export class AccountStore {
  constructor({environment,uid,db,request,onChange=()=>{},onStatus=()=>{},now=Date.now,random=Math.random}) {
    Object.assign(this,{environment,uid,db,request,onChange,onStatus,now,random});
    this.identity=`${environment}:${uid}`;this.session=blank();this.active=true;this.running=null;this.serial=Promise.resolve();
    this.status='connecting';this.timer=0;this.progressSent=new Map();
  }
  async update(change) {
    const result=this.serial.then(()=>transact(this.db,this.uid,change));
    this.serial=result.catch(()=>{});
    const next=await result;
    const changed=JSON.stringify(this.session)!==JSON.stringify(next);
    this.session=next;
    if (this.active&&changed) this.onChange();
    return this.session;
  }
  async start() { await this.update(s=>s);await this.pull();this.schedule(1000);return this; }
  setStatus(value) { this.status=value;if(this.active)this.onStatus(value); }
  effective(kind,id) {
    const key=keyOf(kind,id),pending=this.session.outbox.filter(o=>o.key===key).at(-1);
    const record=this.session.records[key];
    if (pending) return {...record,kind,id,value:pending.value,deleted:pending.deleted};
    return record;
  }
  readLegacy(k) {
    const keys=globalThis.TorahPodStorage?.keys||{follows:'torahpod:v1:follows',saved:'torahpod:v1:saved-episodes',states:'torahpod:v1:episode-state',last:'torahpod-last-episode',progress:'torahpod-progress:'};
    const ids=new Set([...Object.keys(this.session.records),...this.session.outbox.map(o=>o.key)]);
    if(k===keys.last) {
      const id=this.session.last||[...ids].filter(x=>x.startsWith('progress:')).sort((a,b)=>(this.session.records[b]?.updatedAt||0)-(this.session.records[a]?.updatedAt||0))[0]?.slice(9);
      const r=id&&this.effective('progress',id);return r&&!r.deleted?{...this.session.metadata[keyOf('progress',id)],id,...r.value,updatedAt:r.value.recordedAt||r.updatedAt}:null;
    }
    if(k===keys.follows||k===keys.saved) {
      const kind=k===keys.follows?'follows':'saved';
      return [...ids].filter(x=>x.startsWith(`${kind}:`)).map(x=>this.effective(kind,x.slice(kind.length+1)))
        .filter(r=>r&&!r.deleted).map(r=>({...this.session.metadata[keyOf(kind,r.id)],...r.value,...(kind==='follows'?{slug:r.id}:{id:r.id})}));
    }
    if(k.startsWith(keys.progress)) {
      const id=k.slice(keys.progress.length),r=this.effective('progress',id);
      return r&&!r.deleted?{...this.session.metadata[keyOf('progress',id)],id,...r.value,updatedAt:r.value.recordedAt||r.updatedAt}:null;
    }
    if(k===keys.states) return Object.fromEntries([...ids].filter(x=>x.startsWith('progress:')).map(x=>{
      const id=x.slice(9),r=this.effective('progress',id);return [id,{played:r?.value.completed===true,updatedAt:r?.updatedAt||0}];
    }));
    return null;
  }
  async enqueue(kind,id,value,deleted=false,metadata=null,force=false,automatic=false) {
    if(!this.active) return;
    const key=keyOf(kind,id);
    await this.update(s=>{
      if(automatic&&s.resumeSelections?.[id])return s;
      const pending=s.outbox.filter(o=>o.key===key),last=pending.at(-1);
      if(metadata) s.metadata[key]={...metadata};
      if(last && !last.attempted && kind==='progress') {
        last.value=value;last.deleted=deleted;last.force||=force;last.nextAttempt=0;
      } else {
        const expectedRevision=last?last.expectedRevision+1:(s.records[key]?.revision||0);
        s.outbox.push({key,kind,id,value,deleted,expectedRevision,operationId:crypto.randomUUID(),
          attempted:false,attempts:0,nextAttempt:0,force});
      }
      if(kind==='progress')s.last=id;
      return s;
    });
    this.schedule(50);
  }
  async writeLegacy(k,value,remove=false) {
    const keys=globalThis.TorahPodStorage.keys;
    if(k===keys.last) { await this.update(s=>{s.last=remove?null:value?.id;return s;});return; }
    if(k.startsWith(keys.progress)) {
      const id=k.slice(keys.progress.length);
      if(!remove&&this.progressHeld(id))return;
      if(remove)await this.beginPlayback(id);
      await this.enqueue('progress',id,progress(remove?{position:0,duration:0,completed:false}:value),false,value,remove||value?.completed===true,!remove);return;
    }
    if(k===keys.states) {
      const prior=this.readLegacy(k)||{};
      for(const [id,state] of Object.entries(value||{})) if(prior[id]?.played!==state.played) {
        await this.beginPlayback(id);
        const old=this.readLegacy(`${keys.progress}${id}`)||{};
        await this.enqueue('progress',id,progress({...old,completed:state.played,updatedAt:state.updatedAt}),false,old,true);
      }
      return;
    }
    const kind=k===keys.follows?'follows':'saved',prior=this.readLegacy(k)||[];
    const idOf=item=>kind==='follows'?item.slug:item.id;
    const incoming=new Map((remove?[]:value||[]).map(item=>[idOf(item),item]));
    for(const item of prior) if(!incoming.has(idOf(item))) await this.enqueue(kind,idOf(item),{},true);
    for(const [id,item] of incoming) if(!prior.some(old=>idOf(old)===id)) await this.enqueue(kind,id,{},false,item);
  }
  progressHeld(id) {return this.session.resumeSelections?.[id]===true;}
  async beginPlayback(id) {await this.update(s=>{if(s.resumeSelections)delete s.resumeSelections[id];return s;});}
  schedule(delay=1000) {
    if(!this.active)return;clearTimeout(this.timer);
    this.timer=setTimeout(()=>this.flush().catch(()=>{}),delay);
  }
  async pull() {
    if(!this.active)return;
    let cursor=this.session.cursor,until=null,more=true;
    while(more&&this.active) {
      const page=await this.request(`/library?cursor=${cursor}${until===null?'':`&until=${until}`}`);
      await this.update(s=>{
        for(const record of page.records) {
          const key=keyOf(record.kind,record.id);
          if((s.records[key]?.revision||0)<=record.revision)s.records[key]=record;
        }
        s.cursor=page.cursor;return s;
      });
      cursor=page.cursor;until=page.until;more=page.hasMore;
    }
  }
  flush(force=false) {
    if(!this.active)return Promise.resolve();
    if(this.running)return this.running.then(()=>force?this.flush(true):undefined);
    this.running=this.deliver(force).finally(()=>{this.running=null;});return this.running;
  }
  async deliver(force) {
    try {
      await this.serial;
      await this.update(s=>s); // Reload another tab's durable mutations.
      for(const candidate of [...this.session.outbox]) {
        if(!this.active)break;
        let op=this.session.outbox.find(o=>o.operationId===candidate.operationId);
        if(!op||this.session.conflicts[op.key]||op.nextAttempt>this.now())continue;
        if(this.session.outbox.some(o=>o.key===op.key&&o!==op&&this.session.outbox.indexOf(o)<this.session.outbox.indexOf(op)))continue;
        if(op.kind==='progress'&&!force&&!op.force&&this.now()-(this.progressSent.get(op.id)||0)<15000)continue;
        const operationId=op.operationId;
        await this.update(s=>{const item=s.outbox.find(o=>o.operationId===operationId);if(item)item.attempted=true;return s;});
        // Snapshot the value actually sealed by the IndexedDB transaction. A
        // second tab may coalesce an unsent value before this transaction.
        op=clone(this.session.outbox.find(o=>o.operationId===operationId));
        if(!op)continue;
        try {
          const result=await this.request(`/${op.kind}/${encodeURIComponent(op.id)}`,{method:op.deleted?'DELETE':'PUT',
            body:{operationId:op.operationId,expectedRevision:op.expectedRevision,value:op.value}});
          await this.update(s=>{s.outbox=s.outbox.filter(o=>o.operationId!==op.operationId);
            if((s.records[op.key]?.revision||0)<=result.revision)s.records[op.key]=result;return s;});
          if(op.kind==='progress')this.progressSent.set(op.id,this.now());
        } catch(error) {
          if(error.status===409) {
            await this.update(s=>{s.conflicts[op.key]={cloud:error.body?.current||null,local:clone(s.outbox.filter(o=>o.key===op.key).at(-1)||op)};return s;});
            this.setStatus('conflict');continue;
          }
          if(error.status===401&&error.body?.error==='account_deleted') {this.setStatus('deleted');return;}
          if(error.status===401) { this.setStatus('reauthentication');return; }
          if(error.status===403&&error.body?.error==='account_deleted') {this.setStatus('deleted');return;}
          await this.update(s=>{const item=s.outbox.find(o=>o.operationId===op.operationId);if(item){item.attempts++;
            item.nextAttempt=this.now()+Math.min(300000,1000*2**Math.min(item.attempts,8))*(0.5+this.random());}return s;});
          this.setStatus('offline');return;
        }
      }
      await this.pull();
      this.setStatus(Object.keys(this.session.conflicts).length?'conflict':this.session.outbox.length?'pending':'synced');
    } catch(error) { this.setStatus(error.status===401?(error.body?.error==='account_deleted'?'deleted':'reauthentication'):'offline'); }
    finally {this.schedule(15000);}
  }
  async resolve(key,useDevice) {
    const conflict=this.session.conflicts[key];if(!conflict)return;
    await this.update(s=>{s.outbox=s.outbox.filter(o=>o.key!==key);delete s.conflicts[key];
      if(!useDevice&&conflict.local.kind==='progress'){s.resumeSelections||={};s.resumeSelections[conflict.local.id]=true;}
      if(conflict.cloud)s.records[key]=conflict.cloud;else delete s.records[key];return s;});
    if(useDevice)await this.enqueue(conflict.local.kind,conflict.local.id,conflict.local.value,conflict.local.deleted,null,true);
    this.schedule(50);
  }
  async importGuest(records) {
    if(!this.session.importJob)await this.update(s=>{s.importJob={id:crypto.randomUUID(),records:clone(records),offset:0};return s;});
    while(this.session.importJob&&this.active) {
      const job=this.session.importJob,batch=job.records.slice(job.offset,job.offset+50);
      if(!batch.length) {await this.update(s=>{s.importChoice='imported';s.importJob=null;return s;});break;}
      await this.request('/import',{method:'POST',body:{importId:`${job.id}:${job.offset}`,records:batch.map(({kind,id,value})=>({kind,id,value}))}});
      await this.update(s=>{for(const item of batch)if(item.metadata)s.metadata[keyOf(item.kind,item.id)]=item.metadata;s.importJob.offset+=batch.length;return s;});
    }
    await this.pull();
  }
  async stop(clear=true) {
    this.active=false;clearTimeout(this.timer);await this.running;await this.serial;
    if(clear)await transact(this.db,this.uid,()=>null);
  }
}
