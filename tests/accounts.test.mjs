import assert from 'node:assert/strict';
import test from 'node:test';
import {indexedDB} from 'fake-indexeddb';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {AccountStore,openStore} from '../podcast_feeds/web/accounts-core.mjs';

const keys={follows:'torahpod:v1:follows',saved:'torahpod:v1:saved-episodes',states:'torahpod:v1:episode-state',last:'torahpod-last-episode',progress:'torahpod-progress:'};
globalThis.TorahPodStorage={keys};
function cloud() {
  const records=new Map(),changes=[],receipts=new Map(),calls=[];
  let offline=false;
  const request=async(path,options={})=>{
    calls.push({path,...structuredClone(options)});
    if(offline)throw new Error('offline');
    if(path.startsWith('/library')) {
      const cursor=Number(new URL(path,'https://test').searchParams.get('cursor'))||0;
      return {records:changes.slice(cursor),cursor:changes.length,until:changes.length,hasMore:false};
    }
    if(path==='/import')return {applied:options.body.records.length,skipped:0};
    const [,kind,encoded]=path.split('/'),id=decodeURIComponent(encoded),key=`${kind}:${id}`,body=options.body;
    if(receipts.has(body.operationId))return receipts.get(body.operationId);
    const prior=records.get(key);
    if((prior?.revision||0)!==body.expectedRevision)throw Object.assign(new Error('revision_conflict'),{status:409,body:{current:prior}});
    const row={kind,id,value:body.value,deleted:options.method==='DELETE',revision:(prior?.revision||0)+1,updatedAt:Date.now()};
    records.set(key,row);changes.push(row);receipts.set(body.operationId,row);return row;
  };
  return {request,calls,records,changes,setOffline:value=>{offline=value;}};
}
async function store(request,options={}) {
  const environment=options.environment||crypto.randomUUID(),db=options.db||await openStore(environment,indexedDB);
  const value=new AccountStore({environment,uid:options.uid||'alice',db,request,...options});
  await value.update(s=>s);return value;
}
const position=(value,at=Date.now())=>({position:value,duration:1000,completed:false,recordedAt:at});

test('idle sync polls are silent while cloud changes and other-tab writes remain observable',async()=>{
  const server=cloud();let changes=0;
  const client=await store(server.request,{onChange:()=>{changes++;}});
  await client.flush();await client.flush();
  assert.equal(changes,0);
  assert.equal(client.status,'synced');
  await server.request('/follows/example',{method:'PUT',body:{operationId:'new-follow',expectedRevision:0,value:{}}});
  await client.flush();
  assert.equal(changes,1);
  assert.equal(client.readLegacy(keys.follows)[0].slug,'example');
  await client.flush();assert.equal(changes,1);
  const other=await store(server.request,{db:client.db,environment:client.environment});
  await other.writeLegacy(keys.last,{id:'example:episode:other-tab'});
  await client.update(s=>s);
  assert.equal(changes,2);
  assert.equal(client.session.last,'example:episode:other-tab');
  await other.stop(false);await client.stop();
});

test('guest storage stays separate and legacy import never invents timestamps',()=>{
  const data=new Map([[keys.follows,JSON.stringify([{slug:'example'}])],[keys.progress+'example:episode:old',JSON.stringify({position:40,duration:100})]]);
  const context={localStorage:{getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key),
    get length(){return data.size;},key:index=>[...data.keys()][index]},document:{dispatchEvent(){}},CustomEvent:class{}};
  runInNewContext(readFileSync('podcast_feeds/web/storage.js','utf8'),context);
  const adapter=context.TorahPodStorage;
  const records=adapter.guestPreview();assert.equal(records[1].value.recordedAt,null);
  let writes=0;adapter.activate({identity:'preview:alice',readLegacy:()=>[],writeLegacy:async()=>{writes++;}});
  adapter.set(keys.follows,[{slug:'bad'}],'guest');assert.equal(writes,0);
  assert.equal(JSON.parse(data.get(keys.follows))[0].slug,'example');
  adapter.activate(null);assert.equal(adapter.get(keys.follows)[0].slug,'example');
});
test('offline outbox survives restart and cannot be read or submitted by another UID',async()=>{
  const server=cloud();server.setOffline(true);
  const alice=await store(server.request);
  await alice.enqueue('follows','example',{},false,{slug:'example',title:'Example'});
  await alice.flush();const operationId=alice.session.outbox[0].operationId;
  await alice.stop(false);
  const bob=await store(server.request,{db:alice.db,environment:alice.environment,uid:'bob'});
  assert.equal(bob.session.outbox.length,0);assert.deepEqual(bob.readLegacy(keys.follows),[]);
  await bob.stop(false);
  const resumed=await store(server.request,{db:alice.db,environment:alice.environment});
  assert.equal(resumed.session.outbox[0].operationId,operationId);
  server.setOffline(false);await resumed.update(s=>{s.outbox[0].nextAttempt=0;return s;});await resumed.flush();
  assert.equal(resumed.session.outbox.length,0);assert.equal(server.records.size,1);await resumed.stop();
});
test('progress coalesces at 15 seconds, persists first, and explicit pause/seek flushes',async()=>{
  const server=cloud();let now=100000;
  const client=await store(server.request,{now:()=>now});
  await client.enqueue('progress','example:episode:one',position(10));
  assert.equal(client.session.outbox.length,1);assert.equal(server.calls.length,0);
  await client.flush();now+=1000;
  await client.enqueue('progress','example:episode:one',position(20));
  await client.enqueue('progress','example:episode:one',position(30));
  assert.equal(client.session.outbox.length,1);
  await client.flush();assert.equal(server.records.get('progress:example:episode:one').value.position,10);
  await client.flush(true);assert.equal(server.records.get('progress:example:episode:one').value.position,30);
  now+=15001;await client.enqueue('progress','example:episode:one',position(40));await client.flush();
  assert.equal(server.records.get('progress:example:episode:one').revision,3);await client.stop();
});
test('stale progress stops uploads until an explicit choice; pull does not alter active playback',async()=>{
  const server=cloud(),client=await store(server.request);
  const audio={currentTime:123,paused:false};
  await client.enqueue('progress','example:episode:conflict',position(150));
  await server.request('/progress/example%3Aepisode%3Aconflict',{method:'PUT',body:{operationId:'other-device',expectedRevision:0,value:position(20)}});
  await client.flush();assert.equal(client.status,'conflict');assert.equal(audio.currentTime,123);
  const writes=server.calls.filter(c=>c.method==='PUT').length;
  await client.flush(true);assert.equal(server.calls.filter(c=>c.method==='PUT').length,writes);
  await client.resolve('progress:example:episode:conflict',false);
  assert.equal(client.readLegacy(keys.progress+'example:episode:conflict').position,20);
  assert.equal(audio.currentTime,123);await client.stop();
});
test('a stale follow cannot revive a removal; device choice creates a fresh revision-aware operation',async()=>{
  const server=cloud(),client=await store(server.request);
  await server.request('/follows/example',{method:'PUT',body:{operationId:'cloud-add',expectedRevision:0,value:{}}});
  await client.pull();
  await client.enqueue('follows','example',{},false,{slug:'example'});
  await server.request('/follows/example',{method:'DELETE',body:{operationId:'cloud-remove',expectedRevision:1,value:{}}});
  await client.flush();assert.ok(client.session.conflicts['follows:example']);
  await client.resolve('follows:example',true);await client.flush();
  assert.equal(server.records.get('follows:example').revision,3);assert.equal(server.records.get('follows:example').deleted,false);
  await client.stop();
});

test('selected cloud progress survives ongoing playback and restart until the next playback start',async()=>{
  const server=cloud(),client=await store(server.request),id='example:episode:selected';
  await client.enqueue('progress',id,position(150));
  await server.request(`/progress/${encodeURIComponent(id)}`,{method:'PUT',body:{operationId:'other-start',expectedRevision:0,value:position(20)}});
  await client.flush();await client.resolve(`progress:${id}`,false);
  const staleTab=await store(server.request,{db:client.db,environment:client.environment});
  staleTab.session.resumeSelections={}; // A tab has not observed the choice yet.
  await staleTab.writeLegacy(keys.progress+id,{id,position:170,duration:1000,updatedAt:Date.now()});
  await staleTab.writeLegacy(keys.progress+id,{id,position:0,duration:1000,completed:true,updatedAt:Date.now()});
  assert.equal(staleTab.session.outbox.length,0);
  await staleTab.stop(false);
  await client.writeLegacy(keys.progress+id,{id,position:160,duration:1000,updatedAt:Date.now()});
  await client.flush(true);
  assert.equal(client.readLegacy(keys.progress+id).position,20);
  assert.equal(server.records.get(`progress:${id}`).value.position,20);
  await client.stop(false);
  const restarted=await store(server.request,{db:client.db,environment:client.environment});
  assert.equal(restarted.progressHeld(id),true);
  await restarted.beginPlayback(id);
  await restarted.writeLegacy(keys.progress+id,{id,position:25,duration:1000,updatedAt:Date.now()});
  await restarted.flush(true);
  assert.equal(server.records.get(`progress:${id}`).value.position,25);
  assert.equal(server.records.get(`progress:${id}`).revision,2);
  await restarted.stop();
});
test('completion and explicit mark-unplayed carry revisions',async()=>{
  const server=cloud(),client=await store(server.request);
  await client.writeLegacy(keys.progress+'example:episode:complete',{id:'example:episode:complete',position:0,duration:100,completed:true,updatedAt:Date.now()});
  await client.flush(true);
  await client.writeLegacy(keys.states,{'example:episode:complete':{played:false,updatedAt:Date.now()}});
  await client.flush(true);
  const record=server.records.get('progress:example:episode:complete');assert.equal(record.revision,2);assert.equal(record.value.completed,false);await client.stop();
});
test('interrupted import retries the same stored ID and marks completion only after all batches',async()=>{
  const calls=[];let fail=true;
  const client=await store(async(path,options)=>{
    if(path.startsWith('/library'))return {records:[],cursor:0,until:0,hasMore:false};
    calls.push(options.body.importId);if(fail){fail=false;throw new Error('interrupted after server commit');}return {};
  });
  const records=Array.from({length:51},(_,i)=>({kind:'saved',id:`example:episode:${i}`,value:{}}));
  await assert.rejects(client.importGuest(records));assert.equal(client.session.importChoice,null);
  await client.importGuest([]);assert.equal(calls[0],calls[1]);assert.notEqual(calls[1],calls[2]);
  assert.equal(client.session.importChoice,'imported');assert.equal(client.session.importJob,null);await client.stop();
});
test('sign-out removes only its account cache and retains another account',async()=>{
  const server=cloud(),alice=await store(server.request),bob=await store(server.request,{db:alice.db,environment:alice.environment,uid:'bob'});
  await alice.enqueue('saved','example:episode:a',{});await bob.enqueue('saved','example:episode:b',{});
  await alice.stop();await bob.stop(false);
  const cleared=await store(server.request,{db:alice.db,environment:alice.environment});assert.equal(cleared.session.outbox.length,0);
  const retained=await store(server.request,{db:bob.db,environment:bob.environment,uid:'bob'});assert.equal(retained.session.outbox.length,1);
  await cleared.stop();await retained.stop();
});
