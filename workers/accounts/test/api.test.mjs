import assert from 'node:assert/strict';
import {test,before,after} from 'node:test';
import {readFileSync} from 'node:fs';
import {Miniflare} from 'miniflare';
import {generateKeyPair,SignJWT} from 'jose';
import {createHandler} from '../src/index.mjs';
import {authenticate,checkAccount} from '../src/auth.mjs';
import {runDeletionJobs} from '../src/deletion.mjs';

let mf,db,keys;
const project='accounts-test',origin='https://preview.example.com';
const allow={limit:async()=>({success:true})};
let lookupUser={localId:'alice',displayName:'Alice',validSince:'0'};
const googleCall=async(_env,_method,{localId})=>({users:localId.map(uid=>({...lookupUser,localId:uid}))});
const handler=createHandler((request,env,options)=>authenticate(request,env,{...options,keys:keys.publicKey,call:googleCall}),async()=>{});
let env;
before(async()=>{
  keys=await generateKeyPair('RS256');
  mf=new Miniflare({modules:true,script:'export default {fetch(){return new Response("ok")}}',compatibilityDate:'2026-07-01',d1Databases:['DB']});
  db=await mf.getD1Database('DB');
  const sql=readFileSync('workers/accounts/migrations/0001_accounts.sql','utf8');
  // D1 exec executes one statement per line; preserve complete SQL triggers.
  const statements=[];let buffer='',trigger=false;
  for(const line of sql.replace(/--[^\n]*/g,'').split('\n')) {
    if(line.startsWith('CREATE TRIGGER'))trigger=true;
    buffer+=line+'\n';
    if((trigger?/^END;\s*$/.test(line):/;\s*$/.test(line))&&buffer.trim()) {statements.push(buffer);buffer='';trigger=false;}
  }
  for(const statement of statements)await db.prepare(statement.trim()).run();
  env={DB:db,FIREBASE_PROJECT_ID:project,ENVIRONMENT:'preview',LISTENER_ACCOUNTS:'true',PUBLISHER_ACCESS:'true',
    ALLOWED_ORIGINS:origin,IP_LIMITER:allow,USER_LIMITER:allow,PUBLISHER_LIMITER:allow,INTERNAL_LIMITER:allow,
    INTERNAL_STATUS_TOKEN:'test-internal',PUBLISHER_SERVICE_TOKEN:'test-service'};
});
after(async()=>{await mf?.dispose();});
async function token(uid='alice',overrides={}) {
  const now=Math.floor(Date.now()/1000);
  return new SignJWT({sub:uid,iat:now,exp:now+3600,auth_time:now,firebase:{sign_in_provider:'google.com'},...overrides})
    .setProtectedHeader({alg:'RS256',kid:'test'}).setIssuer(overrides.iss||`https://securetoken.google.com/${project}`).setAudience(overrides.aud||project).sign(keys.privateKey);
}
async function call(path,{uid='alice',method='GET',body,headers={},bearer,environment=env}={}) {
  const request=new Request(`https://api.example/api/v1${path}`,{method,headers:{Origin:origin,Authorization:`Bearer ${bearer||await token(uid)}`,
    ...(body?{'Content-Type':'application/json'}:{}),...headers},body:body?JSON.stringify(body):undefined});
  return handler(request,environment,{waitUntil(){}});
}
async function json(response){return response.json();}
const mutation=(operationId,expectedRevision,value={})=>({operationId,expectedRevision,value});
const position=(value,recordedAt=Date.now())=>({position:value,duration:1000,completed:false,recordedAt});

test('verified profiles and exact origins; wrong projects, expiry and forged tokens fail',async()=>{
  const me=await call('/me');assert.equal(me.status,200);assert.equal((await json(me)).uid,'alice');
  assert.equal(me.headers.get('Cache-Control'),'private, no-store');
  assert.equal((await call('/me',{headers:{Origin:'https://preview.example.com.evil'}})).status,403);
  assert.equal((await call('/me',{bearer:await token('alice',{aud:'other'})})).status,401);
  assert.equal((await call('/me',{bearer:await token('alice',{exp:1})})).status,401);
  assert.equal((await call('/me',{bearer:'bad.payload.signature'})).status,401);
  assert.equal((await call('/me',{bearer:await token('alice',{iat:Math.floor(Date.now()/1000)+60})})).status,401);
});
test('disabled, deleted and revoked users fail fresh lookup',async()=>{
  const now=Math.floor(Date.now()/1000),claims={sub:'revoked',auth_time:now-10};
  await assert.rejects(checkAccount(env,claims,true,async()=>({users:[{localId:'revoked',disabled:true}]})),e=>e.status===401);
  await assert.rejects(checkAccount(env,claims,true,async()=>({users:[]})),e=>e.code==='account_deleted');
  await assert.rejects(checkAccount(env,claims,true,async()=>({users:[{localId:'revoked',validSince:String(now)}]})),e=>e.status===401);
});
test('flags are independent and rate limit failure denies requests',async()=>{
  assert.equal((await call('/library',{environment:{...env,LISTENER_ACCOUNTS:'false'}})).status,404);
  assert.equal((await call('/me',{environment:{...env,LISTENER_ACCOUNTS:'false'}})).status,200);
  assert.equal((await call('/publisher/shows',{environment:{...env,PUBLISHER_ACCESS:'false'}})).status,404);
  assert.equal((await call('/me',{environment:{...env,IP_LIMITER:{limit:async()=>({success:false})}}})).status,429);
});
test('mutation retries are atomic, CAS conflicts carry current state, and users are isolated',async()=>{
  const body=mutation('follow-one',0);
  const first=await json(await call('/follows/example',{method:'PUT',body}));assert.equal(first.revision,1);
  assert.deepEqual(await json(await call('/follows/example',{method:'PUT',body})),first);
  assert.equal((await call('/follows/example',{method:'DELETE',body})).status,409);
  const stale=await call('/follows/example',{method:'DELETE',body:mutation('stale',0)});
  assert.equal(stale.status,409);assert.equal((await json(stale)).current.revision,1);
  assert.equal((await json(await call('/library',{uid:'bob'}))).records.length,0);
  const removed=await json(await call('/follows/example',{method:'DELETE',body:mutation('remove-one',1)}));assert.equal(removed.deleted,true);
  const page=await json(await call('/library?limit=1'));assert.equal(page.hasMore,true);
  const next=await json(await call(`/library?cursor=${page.cursor}&until=${page.until}`));assert.equal(next.records.at(-1).deleted,true);
});
test('concurrent writes yield one winner and one conflict',async()=>{
  const replies=await Promise.all(['race-a','race-b'].map(id=>call('/progress/example:episode:race',{method:'PUT',body:mutation(id,0,position(30))})));
  assert.deepEqual(replies.map(r=>r.status).sort(),[200,409]);
  const receipts=await db.prepare("SELECT COUNT(*) n FROM operations WHERE uid='alice' AND item_id='example:episode:race'").first();assert.equal(receipts.n,1);
});
test('guest import preserves tombstones, unknown times, cloud ties and deterministic retries',async()=>{
  const id='example:episode:import',at=Date.now()-1000;
  await call(`/progress/${encodeURIComponent(id)}`,{method:'PUT',body:mutation('cloud-import',0,position(100,at))});
  const records=[{kind:'follows',id:'example',value:{}},{kind:'progress',id,value:position(200,at)},
    {kind:'progress',id:'example:episode:legacy',value:position(50,null)}];
  const body={importId:'import-a',records};
  const one=await call('/import',{method:'POST',body});assert.equal(one.status,200);assert.deepEqual(await json(one),{applied:1,skipped:2});
  assert.deepEqual(await json(await call('/import',{method:'POST',body})),{applied:1,skipped:2});
  const progress=await db.prepare('SELECT value FROM library WHERE uid=? AND kind=? AND item_id=?').bind('alice','progress',id).first();assert.equal(JSON.parse(progress.value).position,100);
  assert.equal((await call('/import',{method:'POST',body:{...body,records:[]}})).status,409);
});
test('publisher issue delivery reconciles uncertain retries and never discloses private fields',async()=>{
  let calls=0;
  const service={fetch:async(_url,options)=>{const raw=JSON.parse(options.body);calls++;assert.equal(raw.uid,'alice');
    assert.equal(raw.allowCreate,calls===1);if(calls===1)throw new Error('network interrupted after creation');return new Response(JSON.stringify({delivered:true}));}};
  const environment={...env,ONBOARDING:service};
  const body={operationId:'submit-id',payload:{source:'feed',sourceUrl:'https://feed.example/rss',contact:'private@example.com',turnstileToken:'first'}};
  assert.equal((await call('/publisher/requests',{method:'POST',body,environment})).status,503);
  await db.prepare('UPDATE publisher_requests SET lease_until=0 WHERE uid=?').bind('alice').run();
  const retry=await call('/publisher/requests',{method:'POST',body:{...body,payload:{...body.payload,turnstileToken:'refreshed'}},environment});assert.equal(retry.status,201);
  const result=await json(retry);assert.equal(JSON.stringify(result).includes('private@example'),false);
  assert.equal((await call(`/publisher/requests/${result.id}`,{uid:'bob'})).status,404);
  const count=await db.prepare('SELECT COUNT(*) n FROM publisher_requests WHERE uid=? AND operation_id=?').bind('alice','submit-id').first();assert.equal(count.n,1);
});
async function status(body,bearer='test-internal') {
  return handler(new Request('https://api.example/api/v1/internal/publisher/status',{method:'POST',headers:{Authorization:`Bearer ${bearer}`,'Content-Type':'application/json'},body:JSON.stringify(body)}),env);
}
test('definitively rejected publisher drafts are absent from submitted requests',async()=>{
  const environment={...env,ONBOARDING:{fetch:async()=>new Response(JSON.stringify({safeToRetry:true}),{status:400})}};
  const rejected=await call('/publisher/requests',{method:'POST',environment,body:{operationId:'rejected-draft',payload:{source:'invalid'}}});
  assert.equal(rejected.status,400);
  assert.equal((await db.prepare('SELECT COUNT(*) n FROM publisher_requests WHERE operation_id=?').bind('rejected-draft').first()).n,0);
});
test('claims require verified owner approval; replay and older status cannot regress',async()=>{
  const environment={...env,ONBOARDING:{fetch:async()=>new Response(JSON.stringify({delivered:true}))}};
  const claim=await json(await call('/publisher/claims',{method:'POST',environment,body:{operationId:'claim-id',showSlug:'example',payload:{notes:'proof is private'}}}));
  const event={eventId:'event-a',requestId:claim.id,revision:1,status:'approved',showSlug:'example'};
  assert.equal((await status(event,'forged')).status,404);
  assert.equal((await status(event)).status,400);
  assert.equal((await status({...event,verifiedOwnership:true})).status,200);
  assert.equal((await status({...event,verifiedOwnership:true})).status,200);
  assert.equal((await status({...event,eventId:'older',revision:1,status:'submitted'})).status,200);
  assert.equal((await status({...event,eventId:'regression',revision:2,status:'under_review'})).status,409);
  const shows=await json(await call('/publisher/shows'));assert.deepEqual(shows.shows,['example']);
  assert.equal((await json(await call('/publisher/claims'))).requests.every(row=>row.kind==='claim'),true);
  assert.equal((await json(await call('/publisher/claims',{uid:'bob'}))).requests.length,0);
  assert.equal((await status({...event,eventId:'invalid-published',revision:2,status:'published',publicationVerified:true})).status,400);
});
test('export and retryable deletion remove owned data and block cached-token resurrection',async()=>{
  const exported=await json(await call('/export'));assert.equal(exported.profile.uid,'alice');assert.ok(exported.library.length);
  const old=await call('/me',{method:'DELETE',bearer:await token('alice',{auth_time:Math.floor(Date.now()/1000)-301})});assert.equal(old.status,403);
  assert.equal((await call('/me',{method:'DELETE'})).status,202);
  assert.equal((await call('/follows/after-delete',{method:'PUT',body:mutation('blocked',0)})).status,401);
  const failed=await runDeletionJobs(env,async()=>{throw new Error('Google unavailable');});assert.equal(failed.failed,1);
  assert.equal((await db.prepare('SELECT COUNT(*) n FROM library WHERE uid=?').bind('alice').first()).n,0);
  await db.prepare('UPDATE deletion_jobs SET next_attempt=0,lease_until=0').run();
  const complete=await runDeletionJobs(env,async()=>({}));assert.equal(complete.completed,1);
  assert.equal((await db.prepare('SELECT COUNT(*) n FROM accounts WHERE uid=?').bind('alice').first()).n,0);
  assert.equal((await call('/me')).status,401);
});
