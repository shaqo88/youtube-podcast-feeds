const fs = require('node:fs');
const cp = require('node:child_process');
const http = require('node:http');
const zlib = require('node:zlib');
const path = require('node:path');
const assert = require('node:assert/strict');
// Use an existing Playwright installation; this benchmark adds no app dependency.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const outDir = path.join(root, '.search-measurements');
fs.mkdirSync(outDir, {recursive:true});
const ref = process.argv[2] || 'HEAD';
const read = (name) => ref === 'working' ? fs.readFileSync(path.join(root, name)) : cp.execFileSync('git', ['show', `${ref}:${name}`], {cwd:root, maxBuffer:50e6});
let app = read('public/assets/app.js').toString();
const raw = read('public/search-index.json').toString();
const result = {ref, bytes:Buffer.byteLength(raw), gzipBytes:zlib.gzipSync(raw).length, episodes:JSON.parse(raw).episodes.length};
const preparedMode = app.includes('function rankPreparedEpisodes(');
const variant = preparedMode ? 'after' : 'before';
const functions = (preparedMode ? ['normalizeSearchText', 'searchScore', 'prepareSearchText', 'preparedSearchScore', 'rankPreparedEpisodes'] : ['normalizeSearchText', 'searchScore']).map(name => app.match(new RegExp(`  function ${name}[\\s\\S]*?\\n  }`))[0]).join('\n');
// Observe the real result rendering path; no hooks are shipped in the app.
app = app.replace('const renderEpisodes = () => {', 'const renderEpisodes = () => { const benchStart = performance.now();')
  .replace('    const render = async () => {\n      const token = ++resultToken;', '    const render = async () => {\n      window.benchInput = performance.now();\n      const token = ++resultToken;')
  .replace('    };\n    const render = async () => {', '      window.benchRenders.push({query:input.value, ms:performance.now()-benchStart, total:performance.now()-window.benchInput});\n    };\n    const render = async () => {');
const cache = new Map();
const server = http.createServer((req,res)=>{
  let name = decodeURIComponent(new URL(req.url,'http://localhost').pathname).slice(1);
  if (!name || name.endsWith('/')) name += 'index.html';
  if (name.includes('..')) {res.writeHead(400).end(); return;}
  try {
    let data;
    // Latest metadata is a release artifact, absent from the Git tree. Build a
    // deterministic recent-list fixture from the same index for clear/navigation tests.
    if (name === 'metadata/v1/latest.json') data=Buffer.from(JSON.stringify({schema_version:1,shows:JSON.parse(read('public/catalog.json')).map(show=>({...show,latest:JSON.parse(raw).episodes.filter(e=>e.show_slug===show.slug).slice(0,20)}))}));
    else if (name === 'assets/app.js') data=Buffer.from(app);
    else { if(!cache.has(name)) cache.set(name,read('public/'+name)); data=cache.get(name); }
    const type = name.endsWith('.js')?'text/javascript':name.endsWith('.json')?'application/json':name.endsWith('.css')?'text/css':name.endsWith('.html')?'text/html':'application/octet-stream';
    if (name==='search-index.json') {data=zlib.gzipSync(data);res.setHeader('Content-Encoding','gzip');}
    res.writeHead(200, {'Content-Type':type,'Content-Length':data.length,'Cache-Control':'no-store'}).end(data);
  } catch {res.writeHead(404).end();}
});
(async()=>{
 console.log('Starting benchmark',ref);
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({executablePath:process.env.SEARCH_BROWSER,headless:true,timeout:15000});
 console.log('Browser ready',browser.version());
 result.browser=browser.version();
 const context=await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block'});
 await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 const page=await context.newPage();
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await context.addInitScript(()=>{window.benchRenders=[];});
 const cdp=await context.newCDPSession(page);
 await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
 await page.goto(origin+'/search/');
 console.log('Search page loaded');
 await page.waitForTimeout(500);
 // CPU-only measurements in Chromium, on the exact production index/functions.
 result.phases=await page.evaluate(({raw,functions,preparedMode})=>{
   (0,eval)(functions+';window.score=searchScore;window.norm=normalizeSearchText;');
   const times=[]; let episodes;
   for(let i=0;i<12;i++){const t=performance.now();episodes=JSON.parse(raw).episodes;times.push(performance.now()-t);}
   const shows=new Map(Array.from(document.querySelectorAll('[data-show-card]')).map(c=>[c.dataset.showSlug,c.dataset]));
   const prepareStart=performance.now();
   const prepared=preparedMode?episodes.map(item=>{const s=shows.get(item.show_slug);return {item,text:prepareSearchText(item.title,s?.showTitle,s?.showAuthor)};}):null;
   const preparation=performance.now()-prepareStart;
   if(preparedMode) (0,eval)(rankPreparedEpisodes.toString().replace('const tokens =', 'const phaseStart=performance.now(); const tokens =').replace('matches.sort(', 'window.phaseScoring=performance.now()-phaseStart; const phaseSortStart=performance.now(); matches.sort(').replace('return matches.map(({ item }) => item);','window.phaseSorting=performance.now()-phaseSortStart; const phaseMapStart=performance.now(); const result=matches.map(({item})=>item); window.phaseMapping=performance.now()-phaseMapStart; return result;'));
   const rows=[];
   for(let i=0;i<5;i++)for(const input of ['נח','נחמ','נחמן','נחמנסון','פרשת','תורה','ביטחון','תשפ״ז','שַׁבָּת']){
     const query=norm(input), t=performance.now();
     if(preparedMode) { const matched=rankPreparedEpisodes(query,prepared); rows.push({query:input,scoring:window.phaseScoring,filtering:0,sorting:window.phaseSorting,mapping:window.phaseMapping,total:performance.now()-t,count:matched.length}); continue; }
     const scored=episodes.map(item=>{const s=shows.get(item.show_slug);return {...item,score:score(query,item.title,s?.showTitle,s?.showAuthor)};});
     const t1=performance.now(), filtered=scored.filter(item=>item.score>0), t2=performance.now();
     filtered.sort((a,b)=>b.score-a.score||String(b.published).localeCompare(String(a.published)));
     const t3=performance.now();rows.push({query:input,scoring:t1-t,filtering:t2-t1,sorting:t3-t2,total:t3-t,count:filtered.length});
   }
   return {parse:times,preparation,rows};
 },{raw,functions,preparedMode});
 console.log('CPU phases complete');
 // Controlled first index request: 1.6 Mbps download and 150 ms latency.
 await cdp.send('Network.enable');
 await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:200000,uploadThroughput:100000,connectionType:'cellular3g'});
 await page.locator('[data-catalog-search]').fill('נחמנסון');
 await page.waitForFunction(()=>window.benchRenders.some(r=>r.query==='נחמנסון'),{timeout:30000});
 result.cold=await page.evaluate(()=>({render:window.benchRenders.at(-1),resource:performance.getEntriesByType('resource').filter(r=>r.name.endsWith('/search-index.json')).map(r=>({duration:r.duration,transfer:r.transferSize,encoded:r.encodedBodySize,decoded:r.decodedBodySize}))}));
 console.log('Cold search complete');
 await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
 await page.evaluate(()=>window.benchRenders=[]);
 for(let i=0;i<5;i++) for(const query of ['נח','נחמ','נחמן','נחמנסון','פרשת','תורה','ביטחון','תשפ״ז','שַׁבָּת']) {
   await page.locator('[data-catalog-search]').fill(query);
   await page.waitForFunction(q=>window.benchRenders.at(-1)?.query===q,query);
 }
 result.warm=await page.evaluate(()=>window.benchRenders);
 result.layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,status:document.querySelector('[data-search-status]').outerHTML,active:document.activeElement?.outerHTML.slice(0,300),rows:document.querySelector('[data-search-episode-results]').children.length}));
 assert.equal(result.layout.scroll,390,'phone layout must fit the viewport');
 await page.locator('[data-catalog-search]').focus();await page.keyboard.press('Tab');
 result.keyboard=await page.evaluate(()=>({tag:document.activeElement.tagName,href:document.activeElement.getAttribute('href'),text:document.activeElement.textContent}));
 assert.equal(result.keyboard.tag,'A','Tab from search must reach a result link');
 await page.waitForTimeout(700);
 await page.screenshot({path:path.join(outDir,`phone-${variant}.png`),fullPage:false});
 // Fresh page, hold one index request while typing, clearing, and leaving.
 const race=await context.newPage(); await cdp.detach();
 let release,requests=0;
 await race.route('**/search-index.json',async route=>{requests++;await new Promise(r=>release=r);await route.continue();});
 await race.goto(origin+'/search/');await race.waitForTimeout(300);
 await race.locator('[data-catalog-search]').pressSequentially('נחמנסון',{delay:20});
 await race.locator('[data-catalog-search]').fill('');
 release();await race.waitForTimeout(500);
 result.cleared=await race.evaluate(()=>({query:document.querySelector('[data-catalog-search]').value,status:document.querySelector('[data-search-status]').textContent,heading:document.querySelector('[data-search-episode-heading]').textContent,requests:performance.getEntriesByType('resource').filter(r=>r.name.endsWith('/search-index.json')).length}));
 result.indexRequestsWhileTyping=requests;
 assert.equal(requests,1,'rapid typing must share one request');
 assert.equal(result.cleared.query,'');assert.equal(result.cleared.status,'');
 const leaving=await context.newPage();let releaseLeaving;
 await leaving.route('**/search-index.json',async route=>{await new Promise(r=>releaseLeaving=r);await route.continue();});
 await leaving.goto(origin+'/search/');await leaving.waitForTimeout(300);
 await leaving.locator('[data-catalog-search]').fill('פרשת');
 await leaving.waitForFunction(()=>document.querySelector('[data-search-status]').textContent.includes('…'));
 await leaving.locator('a[data-app-route="/"]').first().click();
 await leaving.waitForFunction(()=>!document.querySelector('[data-search-page]'));
 releaseLeaving();await leaving.waitForTimeout(500);
 result.navigation={path:new URL(leaving.url()).pathname,searchPage:await leaving.locator('[data-search-page]').count()};
 assert.equal(result.navigation.searchPage,0);
 // HTTP failure and retry by editing the same query.
 const fail=await context.newPage();let failures=0;
 await fail.route('**/search-index.json',route=>++failures===1?route.fulfill({status:503,body:'Unavailable'}):route.continue());
 await fail.goto(origin+'/search/');await fail.waitForTimeout(200);await fail.locator('[data-catalog-search]').fill('פרשת');await fail.waitForTimeout(500);
 result.failure=await fail.locator('[data-search-status]').textContent();
 await fail.locator('[data-catalog-search]').fill('פרשת נח');await fail.waitForFunction(()=>window.benchRenders.some(r=>r.query==='פרשת נח')); 
 result.recovery={requests:failures,status:await fail.locator('[data-search-status]').textContent(),rows:await fail.locator('[data-search-episode-results] > article').count()};
 assert.equal(result.recovery.requests,2);assert.equal(result.recovery.status,'');assert.ok(result.recovery.rows>0);
 result.errors=errors;
 fs.writeFileSync(path.join(outDir,`results-${variant}.json`),JSON.stringify(result,null,2));
 console.log(JSON.stringify({ref,bytes:result.bytes,gzipBytes:result.gzipBytes,episodes:result.episodes,cold:result.cold,layout:result.layout,failure:result.failure,recovery:result.recovery,errors}));
 await browser.close();server.close();
})().catch(e=>{console.error(e);server.close();process.exit(1);});
