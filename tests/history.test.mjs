import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {indexedDB} from 'fake-indexeddb';
import {AccountStore,openStore} from '../podcast_feeds/web/accounts-core.mjs';

const id='fixture:episode:one';
const metadata={id,title:'Synthetic episode',show:'Fixture',showSlug:'fixture',
  src:'https://example.invalid/episode.mp3',href:'https://example.invalid/episode',duration:300};
const value=(position,recordedAt=Date.now())=>({position,duration:300,completed:false,recordedAt});
const key=`torahpod-progress:${id}`;

function page() {
  const values=new Map(),listeners=new Map(),list={markup:''};
  let savedReads=0;
  const empty={hidden:false,toggleAttribute(name,hidden){this.hidden=hidden;}};
  const tab={dataset:{libraryTab:'history'}};
  const section={},followed={};
  const document={
    addEventListener(name,listener){const group=listeners.get(name)||[];group.push(listener);listeners.set(name,group);},
    dispatchEvent(event){for(const listener of listeners.get(event.type)||[])listener(event);},
    querySelector(selector){if(selector==='[data-library-tab="history"][aria-pressed=true]')return tab.dataset.libraryTab==='history'?tab:null;
      return ({'[data-library-episode-list]':list,'[data-library-tab][aria-pressed=true]':tab,
      '[data-library-episodes]':section,'[data-subscriptions-page]':followed,
      '[data-library-episodes-empty]':empty})[selector]||null;},
  };
  const context={document,CustomEvent:class{constructor(type){this.type=type;}},
    localStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k),
      get length(){return values.size;},key:i=>[...values.keys()][i]},
    safeArray:()=>{savedReads++;return [];},savedKey:'torahpod:v1:saved-episodes',
    replaceEpisodeList:(_list,markup)=>{list.markup=markup;},
    searchEpisodeMarkup:episode=>`<article>${episode.title}</article>`,};
  context.window=context;
  runInNewContext(readFileSync('podcast_feeds/web/storage.js','utf8'),context);
  const source=readFileSync('podcast_feeds/web/listening-pages.js','utf8');
  runInNewContext(source.slice(source.indexOf('  function listeningHistory()'),
    source.indexOf('  function setupListeningPages()')),context);
  assert.match(readFileSync('podcast_feeds/web/app.js','utf8'),
    /addEventListener\("torahpod:progresschange", refreshListeningHistory\)/);
  document.addEventListener('torahpod:progresschange',context.refreshListeningHistory);
  document.addEventListener('torahpod:storagechange',context.renderListeningLibrary);
  globalThis.TorahPodStorage={keys:context.TorahPodStorage.keys};
  return {context,values,list,empty,tab,get savedReads(){return savedReads;}};
}

function cloud(initial=[]) {
  const records=new Map(initial.map(record=>[`progress:${record.id}`,record]));
  let offline=false;
  const request=async(path,options={})=>{
    if(offline)throw new Error('offline');
    if(path.startsWith('/library'))return {records:[...records.values()],cursor:records.size,until:records.size,hasMore:false};
    const [,kind,encoded]=path.split('/'),recordId=decodeURIComponent(encoded),entryKey=`${kind}:${recordId}`;
    const prior=records.get(entryKey);
    if((prior?.revision||0)!==options.body.expectedRevision)
      throw Object.assign(new Error('revision_conflict'),{status:409,body:{current:prior}});
    const record={kind,id:recordId,value:options.body.value,
      deleted:options.method==='DELETE',revision:(prior?.revision||0)+1,updatedAt:Date.now()};
    records.set(entryKey,record);return record;
  };
  return {request,records,setOffline:next=>{offline=next;}};
}
async function account(server,uid='alice',db=null) {
  db ||= await openStore(`history-${crypto.randomUUID()}`,indexedDB);
  const store=new AccountStore({environment:'history-test',uid,db,request:server.request});
  await store.start();return store;
}

test('anonymous History uses guest progress and refreshes as playback advances',()=>{
  const {context,list,empty}=page();
  context.renderListeningLibrary();assert.equal(list.markup,'');
  context.TorahPodStorage.set(key,{...metadata,position:42,updatedAt:100});
  assert.match(list.markup,/Synthetic episode/);assert.equal(empty.hidden,true);
  context.TorahPodStorage.remove(key);
  assert.equal(list.markup,'');assert.equal(empty.hidden,false);
});

test('guest playback writes do not reread or rerender the Saved tab',()=>{
  const fixture=page();
  fixture.tab.dataset.libraryTab='saved';
  fixture.context.renderListeningLibrary();
  const before=fixture.savedReads;
  fixture.context.TorahPodStorage.set(key,{...metadata,position:42,updatedAt:100});
  assert.equal(fixture.savedReads,before);
  fixture.tab.dataset.libraryTab='history';
  fixture.context.renderListeningLibrary();
  assert.match(fixture.list.markup,/Synthetic episode/);
});

test('fresh account hydration renders cloud progress and isolates guest, switch, and sign-out',async()=>{
  const {context,list,values}=page();
  context.TorahPodStorage.set(key,{...metadata,title:'Guest episode',position:20});
  const server=cloud([{kind:'progress',id,value:value(42,100),deleted:false,revision:1,updatedAt:100}]);
  const alice=await account(server);
  alice.onChange=()=>context.document.dispatchEvent(new context.CustomEvent('torahpod:storagechange'));
  context.TorahPodStorage.activate(alice);
  assert.equal(alice.readLegacy(key).position,42);
  assert.equal(list.markup,''); // Metadata is still loading.
  await alice.update(s=>{s.metadata[`progress:${id}`]=metadata;return s;});
  assert.match(list.markup,/Synthetic episode/);
  assert.doesNotMatch(list.markup,/Guest episode/);
  assert.equal(values.get(key).includes('Guest episode'),true);
  const bob=await account(cloud(), 'bob',alice.db);
  context.TorahPodStorage.activate(bob);
  assert.equal(list.markup,'');
  context.TorahPodStorage.activate(null);
  assert.match(list.markup,/Guest episode/);
  await alice.stop(false);await bob.stop(false);
});

test('offline progress appears immediately, reconnects, and a deleted record leaves History',async()=>{
  const {context,list}=page();
  const server=cloud();
  const alice=await account(server);
  alice.onChange=()=>context.document.dispatchEvent(new context.CustomEvent('torahpod:storagechange'));
  context.TorahPodStorage.activate(alice);
  await alice.enqueue('progress',id,value(55),false,metadata);
  assert.match(list.markup,/Synthetic episode/);
  assert.equal(context.TorahPodStorage.get(key).position,55);
  server.setOffline(true);
  await alice.flush(true);
  assert.equal(alice.status,'offline');
  assert.match(list.markup,/Synthetic episode/);
  server.setOffline(false);
  await alice.update(s=>{s.outbox[0].nextAttempt=0;return s;});
  await alice.flush(true);
  assert.equal(server.records.get(`progress:${id}`).value.position,55);
  await alice.enqueue('progress',id,value(0),true,metadata);
  assert.equal(list.markup,'');
  await alice.flush(true);
  assert.equal(list.markup,'');
  await alice.stop();
});

test('a conflicting device update remains visible until the cloud choice replaces it',async()=>{
  const {context,list}=page();
  const server=cloud([{kind:'progress',id,value:value(20),deleted:false,revision:1,updatedAt:100}]);
  const alice=await account(server);
  alice.onChange=()=>context.document.dispatchEvent(new context.CustomEvent('torahpod:storagechange'));
  await alice.update(s=>{s.metadata[`progress:${id}`]=metadata;return s;});
  context.TorahPodStorage.activate(alice);
  await alice.enqueue('progress',id,value(55),false,metadata);
  await server.request(`/progress/${encodeURIComponent(id)}`,
    {method:'PUT',body:{expectedRevision:1,value:value(80)}});
  await alice.flush(true);
  assert.equal(alice.status,'conflict');
  assert.equal(context.TorahPodStorage.get(key).position,55);
  assert.match(list.markup,/Synthetic episode/);
  await alice.resolve(`progress:${id}`,false);
  assert.equal(context.TorahPodStorage.get(key).position,80);
  assert.match(list.markup,/Synthetic episode/);
  await alice.stop();
});

test('stale account success or failure cannot reactivate History after sign-out',async()=>{
  for(const outcome of ['success','failure']) {
    let finishProfile,failProfile;
    const profile=new Promise((resolve,reject)=>{finishProfile=resolve;failProfile=reject;});
    let active='guest';
    let authUid='alice';
    class PendingStore {
      constructor({uid}){this.uid=uid;this.identity=`production:${uid}`;this.active=true;this.session={outbox:[]};}
      async start(){}
      async stop(){this.active=false;}
      async update(){}
      setStatus(){}
      schedule(){}
    }
    const context={user:null,store:null,deleting:false,publisher:null,mode:'',problem:'',publisherAttempt:null,
      config:{environment:'production',listenerAccounts:true,publisherAccess:false},db:{},AccountStore:PendingStore,
      request:()=>profile,closeDeleteDialog(){},render(){},emit(){},hydrate:async()=>{},
      auth:{current:()=>authUid?{uid:authUid}:null,signOut:async()=>{authUid=null;}},localStorage:{setItem(){},removeItem(){}},
      window:{TorahPodStorage:{activate(value){active=value?.identity||'guest';}}}};
    const source=readFileSync('podcast_feeds/web/accounts.mjs','utf8');
    runInNewContext(source.slice(source.indexOf('  async function changed(next)'),
      source.indexOf('  async function loadPublisher()'))+'\nthis.transitions={changed,signout};',context);
    const loading=context.transitions.changed({uid:'alice'});
    await context.transitions.signout(true);
    if(outcome==='success')finishProfile({uid:'alice'});else failProfile(new Error('offline'));
    await loading;
    assert.equal(active,'guest',outcome);
    assert.equal(context.store,null,outcome);
  }
});

test('a stale account response cannot activate after auth switches identity',async()=>{
  let finishAlice;
  const aliceProfile=new Promise(resolve=>{finishAlice=resolve;});
  let authUid='alice';
  const activations=[];
  class PendingStore {
    constructor({uid}){this.uid=uid;this.identity=`production:${uid}`;this.active=true;this.session={outbox:[]};}
    async start(){}
    async stop(){this.active=false;}
  }
  const context={user:null,store:null,deleting:false,publisher:null,mode:'',problem:'',publisherAttempt:null,
    config:{environment:'production',listenerAccounts:true,publisherAccess:false},db:{},AccountStore:PendingStore,
    request:()=>context.user?.uid==='alice'?aliceProfile:Promise.resolve({uid:'bob'}),
    closeDeleteDialog(){},render(){},emit(){},hydrate:async()=>{},
    auth:{current:()=>({uid:authUid})},localStorage:{setItem(){},removeItem(){}},
    window:{TorahPodStorage:{activate(value){activations.push(value?.identity||'guest');}}}};
  const source=readFileSync('podcast_feeds/web/accounts.mjs','utf8');
  runInNewContext(source.slice(source.indexOf('  async function changed(next)'),
    source.indexOf('  async function loadPublisher()'))+'\nthis.transitions={changed};',context);
  const loading=context.transitions.changed({uid:'alice'});
  authUid='bob';finishAlice({uid:'alice'});
  await loading;
  assert.ok(!activations.includes('production:alice'));
  await context.transitions.changed({uid:'bob'});
  assert.equal(activations.at(-1),'production:bob');
});
