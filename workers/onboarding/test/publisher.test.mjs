import assert from 'node:assert/strict';
import test from 'node:test';
import {handlePublisherSubmission} from '../src/index.mjs';

const id='12345678-1234-1234-1234-123456789012';
const payload={source:'youtube',youtubeUrl:'https://www.youtube.com/@example',title:'Example lessons',slug:'example-lessons',speaker:'Example',startDate:'2026-07-19',contact:'owner@example.org',authorizationConfirmed:true,turnstileToken:'challenge'};
const env={PUBLISHER_SERVICE_TOKEN:'service-secret',PUBLISHER_ACCESS:'true',GITHUB_TOKEN:'private-token',ENVIRONMENT:'preview',TURNSTILE_SECRET:'turnstile-secret',TURNSTILE_ALLOWED_HOSTNAMES:'accounts-preview.torah-pod.pages.dev',GLOBAL_SUBMIT_LIMITER:{limit:async()=>({success:true})}};
const body=(extra={})=>({requestId:id,uid:'verified-server-user',environment:'preview',kind:'submission',allowCreate:true,payload,...extra});
const request=(value,secret='service-secret')=>new Request('https://internal.example/internal/publisher',{method:'POST',headers:{'X-Publisher-Service-Token':secret,'Content-Type':'application/json'},body:JSON.stringify(value)});
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
async function mocked(fn,run){const original=globalThis.fetch;globalThis.fetch=fn;try{await run();}finally{globalThis.fetch=original;}}

test('internal intake denies missing secrets and cross-environment input',async()=>{
  await mocked(async()=>{throw new Error('no network');},async()=>{
    assert.equal((await handlePublisherSubmission(request(body(),'wrong'),env)).status,404);
    assert.equal((await handlePublisherSubmission(request(body({environment:'production'})),env)).status,503);
  });
});
test('retry finds the authoritative marker before expired Turnstile and never creates twice',async()=>{
  let creates=0;
  await mocked(async(url,options={})=>{
    if(options.method==='POST')creates++;
    assert.ok(String(url).includes('issues?state=all'));
    return json([{body:`<!-- torahpod-request:${id} -->\nprivate data`,state:'closed'}]);
  },async()=>{
    const response=await handlePublisherSubmission(request(body({allowCreate:false,payload:{}})),env);
    assert.equal(response.status,200);assert.deepEqual(await response.json(),{delivered:true});assert.equal(creates,0);
  });
});
test('ambiguous delivery is reconciliation only even if the marker is absent',async()=>{
  await mocked(async url=>{assert.ok(String(url).includes('issues?state=all'));return json([]);},async()=>{
    const response=await handlePublisherSubmission(request(body({allowCreate:false})),env);
    assert.equal(response.status,202);
  });
});
test('duplicate lookup outage fails closed before private issue creation',async()=>{
  let creates=0;
  await mocked(async(url,options={})=>{
    if(String(url).includes('issues?state=all'))return json([]);
    if(String(url).includes('siteverify'))return json({success:true,action:'onboarding',hostname:'accounts-preview.torah-pod.pages.dev'});
    if(options.method==='POST')creates++;
    return json({error:'dependency'},503);
  },async()=>{assert.equal((await handlePublisherSubmission(request(body()),env)).status,503);assert.equal(creates,0);});
});
test('claim creation remains private and requires manual source verification',async()=>{
  let issue;
  await mocked(async(url,options={})=>{
    if(String(url).includes('issues?state=all'))return json([]);
    if(String(url).includes('siteverify'))return json({success:true,action:'onboarding',hostname:'accounts-preview.torah-pod.pages.dev'});
    if(String(url).includes('/contents/shows/'))return new Response('title: Example');
    if(String(url).endsWith('/issues')){issue=JSON.parse(options.body);return json({number:42},201);}
    throw new Error('unexpected request');
  },async()=>{
    const response=await handlePublisherSubmission(request(body({kind:'claim',showSlug:'example',challenge:`torahpod-claim-${id}`,payload:{...payload,proofUrl:'https://source.example.org/proof'}})),env);
    assert.equal(response.status,201);assert.deepEqual(await response.json(),{delivered:true});
    assert.ok(issue.labels.includes('ownership-claim'));assert.ok(issue.labels.includes('preview-request'));
    assert.ok(issue.body.startsWith(`<!-- torahpod-request:${id} -->\n<!-- torahpod-account:`));
    assert.ok(issue.body.includes('verified-server-user'));assert.ok(issue.body.includes('An email match never establishes ownership'));
    assert.equal(issue.labels.includes('approved'),false);
  });
});
