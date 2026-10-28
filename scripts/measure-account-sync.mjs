// Usage: node scripts/measure-account-sync.mjs [baseline-ref] [playwright-module]
// Playwright is an optional local measurement tool, not an application dependency.
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const baseline=process.argv[2]||'ac6e59de9ca';
const {chromium}=await import(process.argv[3]?pathToFileURL(resolve(process.argv[3])).href:'playwright');
const oldCore=execFileSync('git',['show',`${baseline}:podcast_feeds/web/accounts-core.mjs`],{encoding:'utf8'});
const browser=await chromium.launch({channel:process.platform==='win32'?'msedge':undefined,headless:true});
const epoch=1000000,duration=300000,results=[];
const origin='https://sync-fixture.invalid';
try {
for(const variant of ['before','after'])for(const scenario of ['visible idle','hidden idle','playback','offline reconnect','two tabs','two devices','freshness probes']) {
  const cloud={records:new Map(),changes:[],receipts:new Map(),offline:false,calls:[],uploads:[]};
  let time=epoch;
  const contexts=[],pages=[];
  async function context() {
    const ctx=await browser.newContext();contexts.push(ctx);
    await ctx.route(`${origin}/**`,async route=>{
      const req=route.request(),url=new URL(req.url()),path=url.pathname;
      const respond=(body,status=200,type='application/json')=>route.fulfill({status,contentType:type,body:typeof body==='string'?body:JSON.stringify(body)});
      if(path.startsWith('/api/v1')) {
        const endpoint=path.slice(7),call={time,endpoint,method:req.method(),unchanged:false};cloud.calls.push(call);
        if(cloud.offline){call.failed=true;return route.abort('internetdisconnected');}
        if(endpoint==='/me')return respond({uid:'synthetic-alice'});
        if(endpoint==='/library') {
          const cursor=Number(url.searchParams.get('cursor'))||0,records=cloud.changes.slice(cursor);
          call.unchanged=records.length===0;
          return respond({records,cursor:cloud.changes.length,until:cloud.changes.length,hasMore:false});
        }
        const body=req.postDataJSON(),[,kind,encoded]=endpoint.split('/'),id=decodeURIComponent(encoded),key=`${kind}:${id}`;
        if(cloud.receipts.has(body.operationId))return respond(cloud.receipts.get(body.operationId));
        const prior=cloud.records.get(key);
        if((prior?.revision||0)!==body.expectedRevision)return respond({error:'revision_conflict',current:prior},409);
        const row={kind,id,value:body.value,deleted:req.method()==='DELETE',revision:(prior?.revision||0)+1,updatedAt:time};
        cloud.records.set(key,row);cloud.changes.push(row);cloud.receipts.set(body.operationId,row);
        cloud.uploads.push({time,recordedAt:row.value.recordedAt,kind});return respond(row);
      }
      if(path==='/')return respond('<!doctype html><html lang="en"><body><script src="/assets/storage.js"></script><script type="module" src="/fixture.mjs"></script></body></html>',200,'text/html');
      if(path==='/catalog.json')return respond([]);
      if(path==='/search-index.json')return respond({episodes:[]});
      if(path==='/assets/firebase-auth.bundle.js')return respond("export function createAuth(){const user={uid:'synthetic-alice'};return {current:()=>user,token:async()=> 'synthetic-token',subscribe:callback=>callback(user)};}",200,'text/javascript');
      const file=path==='/fixture.mjs'?'tests/fixtures/account-sync-browser.mjs':`podcast_feeds/web/${path.split('/').at(-1)}`;
      return respond(path==='/assets/accounts-core.mjs'&&variant==='before'?oldCore:readFileSync(file,'utf8'),200,'text/javascript');
    });
    return ctx;
  }
  async function page(ctx) {
    const p=await ctx.newPage();pages.push(p);await p.goto(origin);
    await p.waitForFunction(()=>globalThis.client?.status==='connecting'&&globalThis.client?.session);
    // Activation follows start(), so the first poll is already scheduled.
    return p;
  }
  const first=await context();await page(first);
  if(scenario==='two tabs')await page(first);
  if(scenario==='two devices')await page(await context());
  if(scenario==='hidden idle')await pages[0].evaluate(()=>fixture.visibility(true));
  const actions=new Map();
  function at(offset,callback){const list=actions.get(offset)||[];list.push(callback);actions.set(offset,list);}
  if(scenario==='playback')for(let offset=5000;offset<duration;offset+=5000)at(offset,()=>pages[0].evaluate(position=>fixture.progress(position),offset/1000));
  if(scenario==='playback')at(299000,()=>pages[0].evaluate(async()=>{TorahPodStorage.forceProgress();await client.running;}));
  if(scenario==='offline reconnect') {
    at(30000,()=>{cloud.offline=true;});at(40000,()=>pages[0].evaluate(()=>fixture.saved()));
    at(120000,async()=>{cloud.offline=false;await pages[0].evaluate(()=>fixture.online());});
  } else if(!scenario.endsWith('idle'))at(120000,()=>pages[0].evaluate(()=>fixture.saved()));
  const remoteAt=61001;
  if(!scenario.endsWith('idle'))at(remoteAt,()=>{
    const row={kind:'follows',id:'remote-fixture',value:{},deleted:false,revision:1,updatedAt:time};
    cloud.records.set('follows:remote-fixture',row);cloud.changes.push(row);
  });
  let discovered=null,savedDiscovered=null;
  // Advance to actual production deadlines and scenario actions, without
  // wall-clock sleeps or replacing the implementation's scheduling decisions.
  let offset=0;
  while(offset<=duration) {
    time=epoch+offset;
    for(const p of pages)await p.evaluate(target=>fixture.advance(target),time);
    for(const action of actions.get(offset)||[])await action();
    const snapshots=[];
    for(const p of pages)snapshots.push(await p.evaluate(()=>fixture.snapshot()));
    if(discovered===null&&offset>=remoteAt&&snapshots.at(-1).remote)discovered=offset-remoteAt;
    if(savedDiscovered===null&&snapshots.at(-1).saved)savedDiscovered=offset-(scenario==='offline reconnect'?40000:120000);
    if(offset===duration)break;
    const next=snapshots.map(s=>s.next-epoch);
    offset=Math.min(duration,...next,...[...actions.keys()].filter(t=>t>offset));
  }
  const metrics=await Promise.all(pages.map(p=>p.evaluate(()=>({...fixture.metrics,outbox:client.session.outbox.length,cursor:client.session.cursor}))));
  assert.ok(metrics.every(m=>m.outbox===0),'all pending operations delivered');
  if(!scenario.endsWith('idle')) {
    assert.notEqual(discovered,null,'remote change was observed');
    assert.equal(cloud.records.get('saved:fixture:episode:saved')?.revision,1,'one durable saved operation');
  }
  if(pages.length===2)assert.notEqual(savedDiscovered,null,'peer observed the saved change');
  const saved=cloud.uploads.find(x=>x.kind==='saved');
  results.push({variant,scenario,requests:cloud.calls.length,unchanged:cloud.calls.filter(c=>c.unchanged).length,failed:cloud.calls.filter(c=>c.failed).length,
    puts:metrics.reduce((n,m)=>n+m.puts,0),readwrite:metrics.reduce((n,m)=>n+m.readwrite,0),remoteDiscoveryMs:discovered,
    reconnectDiscoveryMs:scenario==='offline reconnect'?discovered-(120000-remoteAt):null,
    peerDiscoveryMs:pages.length===2?savedDiscovered:null,
    savedUploadMs:saved?saved.time-epoch-120000:null,
    maxProgressAgeMs:Math.max(0,...cloud.uploads.filter(x=>x.recordedAt).map(x=>x.time-x.recordedAt))});
  for(const ctx of contexts)await ctx.close();
  console.error(JSON.stringify(results.at(-1)));
}
for(const after of results.filter(row=>row.variant==='after')) {
  const before=results.find(row=>row.variant==='before'&&row.scenario===after.scenario);
  for(const key of ['requests','unchanged','failed','readwrite','remoteDiscoveryMs','reconnectDiscoveryMs','peerDiscoveryMs','savedUploadMs','maxProgressAgeMs'])
    assert.equal(after[key],before[key],`${after.scenario}: unchanged ${key}`);
  assert.ok(after.puts<before.puts,`${after.scenario}: fewer puts`);
  if(after.remoteDiscoveryMs!==null&&after.scenario!=='offline reconnect')assert.ok(after.remoteDiscoveryMs<=15000,'remote freshness bound');
  if(after.scenario==='offline reconnect')assert.equal(after.reconnectDiscoveryMs,0,'online immediately pulls remote data');
  if(after.peerDiscoveryMs!==null)assert.ok(after.peerDiscoveryMs<=15050,'local debounce plus remote freshness bound');
}
console.log(JSON.stringify({baseline,browser:browser.version(),durationMs:duration,results},null,2));
} finally {await browser.close();}
