import {initialize} from '/assets/accounts.mjs';

// Synthetic time controls only application timers; IndexedDB and fetch use the
// browser's real asynchronous implementations. No production services are used.
let now=1000000,sequence=0;
const timers=new Map();
Date.now=()=>now;
Math.random=()=>0.5; // Identical retry jitter for before/after comparisons.
globalThis.setTimeout=(callback,delay=0)=>{const id=++sequence;timers.set(id,{at:now+delay,callback});return id;};
globalThis.clearTimeout=id=>timers.delete(id);
const metrics={puts:0,deletes:0,readwrite:0};
for(const [method,key] of [['put','puts'],['delete','deletes']]) {
  const original=IDBObjectStore.prototype[method];
  IDBObjectStore.prototype[method]=function(...args){metrics[key]++;return original.apply(this,args);};
}
const transaction=IDBDatabase.prototype.transaction;
IDBDatabase.prototype.transaction=function(...args){if(args[1]==='readwrite')metrics.readwrite++;return transaction.apply(this,args);};
const activate=TorahPodStorage.activate;
TorahPodStorage.activate=value=>{globalThis.client=value;activate(value);};
const snapshot=()=>({next:Math.min(Infinity,...[...timers.values()].map(timer=>timer.at)),
  remote:!!globalThis.client?.session.records['follows:remote-fixture'],saved:!!globalThis.client?.session.records['saved:fixture:episode:saved']});
globalThis.fixture={
  metrics,snapshot,
  async advance(target) {
    while(true) {
      const due=[...timers].filter(([,timer])=>timer.at<=target).sort((a,b)=>a[1].at-b[1].at||a[0]-b[0])[0];
      if(!due)break;
      timers.delete(due[0]);now=due[1].at;await due[1].callback();
      await globalThis.client?.serial;await globalThis.client?.running;
    }
    now=target;
    return snapshot();
  },
  async visibility(hidden) {
    Object.defineProperty(document,'visibilityState',{configurable:true,value:hidden?'hidden':'visible'});
    document.dispatchEvent(new Event('visibilitychange'));
    await client.running;
  },
  async progress(position) {
    await client.writeLegacy(TorahPodStorage.keys.progress+'fixture:episode:one',
      {id:'fixture:episode:one',position,duration:1000,updatedAt:now});
    await client.writeLegacy(TorahPodStorage.keys.last,{id:'fixture:episode:one'});
  },
  async saved() {await client.enqueue('saved','fixture:episode:saved',{});},
  async online() {window.dispatchEvent(new Event('online'));await this.advance(now);},
};
await initialize({environment:'preview',apiOrigin:location.origin,firebase:{},listenerAccounts:true,publisherAccess:false},location.origin+'/');
