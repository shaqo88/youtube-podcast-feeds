// Run with node tests/accessibility.browser.mjs. Set PLAYWRIGHT_MODULE and
// CHROMIUM_EXECUTABLE when using an externally installed browser runtime.
// All requests are intercepted: no account, media or production writes occur.
import assert from 'node:assert/strict';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';

const require = createRequire(import.meta.url);
for(const arg of process.argv.slice(2)) {
  const match=arg.match(/^--([A-Z_]+)=(.*)$/);
  if(match) process.env[match[1]]=match[2];
}
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = process.cwd();
const output = path.join(root, 'tmp/accessibility');
await mkdir(output, {recursive:true});
const browser = await chromium.launch({headless:true,
  ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath:process.env.CHROMIUM_EXECUTABLE} : {})});
const baseline = process.env.ACCESSIBILITY_BASELINE === '1';
const results = {baseline, scenarios:[], axe:[]};
// A real, silent, 60-second WAV lets Chromium exercise HTML audio and seeking
// without fetching recordings or substituting HTMLMediaElement methods.
const wav = Buffer.alloc(44 + 8000 * 2 * 60);
wav.write('RIFF'); wav.writeUInt32LE(wav.length-8,4); wav.write('WAVEfmt ',8);
wav.writeUInt32LE(16,16); wav.writeUInt16LE(1,20); wav.writeUInt16LE(1,22);
wav.writeUInt32LE(8000,24); wav.writeUInt32LE(16000,28);
wav.writeUInt16LE(2,32); wav.writeUInt16LE(16,34); wav.write('data',36);
wav.writeUInt32LE(wav.length-44,40);

async function localContext(options={}) {
  const context = await browser.newContext({viewport:{width:390,height:844},serviceWorkers:'block',...options});
  await context.route('**/*',async route=>{
    if(route.request().resourceType()==='media' || route.request().url().endsWith('/fixture.wav')) {
      return route.fulfill({status:200,contentType:'audio/wav',body:wav});
    }
    if(!route.request().url().startsWith('http://local.test/')) return route.abort();
    try {
      let file = path.join(root,'public',decodeURIComponent(new URL(route.request().url()).pathname));
      const {stat} = await import('node:fs/promises');
      if((await stat(file)).isDirectory()) file=path.join(file,'index.html');
      await route.fulfill({status:200,contentType:({'.js':'text/javascript','.json':'application/json','.css':'text/css','.html':'text/html','.woff2':'font/woff2'})[path.extname(file)]||'application/octet-stream',body:await readFile(file)});
    } catch {await route.fulfill({status:404,body:'Not found'});}
  });
  return context;
}
async function focusState(page) {
  return page.evaluate(()=>({tag:document.activeElement.tagName,
    row:document.activeElement.closest('[data-queue-id]')?.dataset.queueId,
    action:document.activeElement.getAttribute('data-queue-delta'),
    name:document.activeElement.getAttribute('aria-label')}));
}
async function noOverflow(page) {
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'horizontal overflow');
}
async function axe(page,name) {
  if(!process.env.AXE_SCRIPT) return;
  // Entrance animations otherwise produce transient contrast failures.
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForTimeout(300);
  await page.addScriptTag({content:await readFile(process.env.AXE_SCRIPT,'utf8')});
  const report=await page.evaluate(async()=>{
    const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}});
    return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:r.incomplete.map(v=>v.id)};
  });
  results.axe.push({name,...report});
}

try {
  const context=await localContext();
  const page=await context.newPage(); page.setDefaultTimeout(10000);
  await page.goto('http://local.test/');
  // Use the real catalog and real queue actions, rather than seeding storage.
  for(let i=0;i<3;i++) await page.locator('[data-queue-add]').nth(i).click();
  await page.locator('.app-bottom-nav a[href$="queue/"]').click();
  await page.waitForURL('**/queue/');
  const ids=await page.locator('[data-queue-id]').evaluateAll(rows=>rows.map(r=>r.dataset.queueId));
  await page.locator('[data-queue-move][data-queue-delta="1"]').first().focus();
  await page.keyboard.press('Enter');
  assert.deepEqual(await page.locator('[data-queue-id]').evaluateAll(rows=>rows.map(r=>r.dataset.queueId)),[ids[1],ids[0],ids[2]]);
  const moved=await focusState(page);
  assert.equal(moved.tag,baseline?'BODY':'BUTTON');
  if(!baseline) {
    assert.equal(moved.row,ids[0]); assert.equal(moved.action,'1');
    // At the boundary the just-used direction is disabled; focus stays in-row.
    await page.keyboard.press('Enter');
    assert.equal((await focusState(page)).row,ids[0]);
    assert.equal(await page.locator('[data-queue-drag-handle][tabindex]').count(),0);
    await page.locator('[data-queue-remove]').last().focus();
    await page.keyboard.press('Enter');
    assert.equal((await focusState(page)).row,ids[2]);
    await page.keyboard.press('Enter');
    assert.equal((await focusState(page)).row,ids[1]);
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('[data-queue-empty]').evaluate(e=>e===document.activeElement),true);
    assert.equal(await page.locator('[data-queue-id]').count(),0);
    await page.goBack(); await page.waitForURL('http://local.test/');
    for(let i=0;i<3;i++) await page.locator('[data-queue-add]').nth(i).click();
    await page.locator('.app-bottom-nav a[href$="queue/"]').click();await page.waitForURL('**/queue/');
    await page.locator('[data-queue-move][data-queue-delta="1"]').first().focus();await page.keyboard.press('Enter');
  }
  results.scenarios.push({name:'queue-keyboard-move-remove',moved});
  await page.screenshot({path:path.join(output,`${baseline?'before':'after'}-queue.png`)});
  await noOverflow(page); await axe(page,'Hebrew phone queue');
  // Escape must dismiss the episode menu without consuming browser history.
  await page.locator('.app-bottom-nav a[data-app-route="/"]').click();await page.waitForURL('http://local.test/');
  const menu=page.locator('.episode-more').first();
  await menu.locator('summary').click();await menu.locator('[data-save-episode]').focus();
  await page.screenshot({path:path.join(output,`${baseline?'before':'after'}-menu-open.png`)});
  await page.keyboard.press('Escape');
  if(baseline) await page.waitForURL('**/queue/');
  else {
    assert.equal(page.url(),'http://local.test/');
    assert.equal(await menu.evaluate(e=>e.open),false);
    assert.equal(await menu.locator('summary').evaluate(e=>e===document.activeElement),true);
    await page.keyboard.press('Escape');assert.equal(page.url(),'http://local.test/');
    // Header dismissal restores the trigger and reports collapsed state.
    await page.locator('[data-nav-menu-toggle]').click();
    await page.locator('[data-theme-select]').focus();await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-nav-menu-toggle]').getAttribute('aria-expanded'),'false');
    assert.equal(await page.locator('[data-nav-menu-toggle]').evaluate(e=>e===document.activeElement),true);
  }
  results.scenarios.push({name:'menu-escape',path:new URL(page.url()).pathname});
  await page.screenshot({path:path.join(output,`${baseline?'before':'after'}-menu-escape.png`)});
  if(!baseline) {
    // Find an episode through search, play it, pause, seek and change speed.
    await page.locator('.app-bottom-nav a[href$="search/"]').click();await page.waitForURL('**/search/');
    const search=page.locator('[data-catalog-search]');
    await search.fill('וירא');
    await page.waitForFunction(()=>!document.querySelector('[data-search-status]')?.textContent.includes('…'));
    await page.locator('[data-episode-id]').first().evaluate(article=>{
      article.dataset.episodeSrc='http://local.test/fixture.wav';
      article.querySelector('audio').dataset.audioSrc='http://local.test/fixture.wav';
    });
    await page.locator('[data-episode-play]').first().click();
    await page.waitForFunction(()=>[...document.querySelectorAll('audio')].some(a=>!a.paused&&a.currentTime>0));
    await page.evaluate(()=>{window.fixtureAudio=[...document.querySelectorAll('audio')].find(a=>!a.paused&&a.currentTime>0);});
    await page.locator('[data-player-toggle]').click();
    assert.equal(await page.evaluate(()=>window.fixtureAudio.paused),true);
    assert.equal(await page.locator('[data-player-toggle]').getAttribute('aria-busy'),'false');
    // Let the asynchronous pause/timeupdate events settle before seeking.
    await page.waitForTimeout(300);
    const seekBefore=await page.evaluate(()=>window.fixtureAudio.currentTime);
    await page.waitForFunction(()=>!document.querySelector('[data-player-seek]').disabled);
    await page.locator('[data-player-seek]').focus();await page.keyboard.press('ArrowUp');
    results.scenarios.push({name:'keyboard-seek',before:seekBefore,...await page.evaluate(()=>{
      const audio=window.fixtureAudio,seek=document.querySelector('[data-player-seek]');
      return {position:audio.currentTime,duration:audio.duration,seekable:audio.seekable.length,value:seek.value,max:seek.max,focused:document.activeElement===seek};
    })});
    // Record media position separately: intercepted WAV seeking is not accepted
    // as a real-media seek test. The existing listening tests cover the handler.
    await page.locator('[data-player-details]').click();
    assert.equal(await page.locator('[data-player]').getAttribute('aria-modal'),'true');
    await page.locator('[data-player-speed]').click();
    assert.equal(await page.evaluate(()=>window.fixtureAudio.playbackRate),1.25);
    await page.locator('[data-player-minimize]').focus();await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('[data-player]').evaluate(e=>e.contains(document.activeElement)),true);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('[data-player-details]').evaluate(e=>e===document.activeElement),true);
    await axe(page,'Hebrew phone search and compact player');
    // A persistent polite status must not churn on every playback tick.
    const announcements=await page.evaluate(async()=>{
      const messages=[];const status=document.querySelector('[data-app-status]');
      const observer=new MutationObserver(()=>messages.push(status.textContent));
      observer.observe(status,{childList:true,subtree:true,characterData:true});
      const a=window.fixtureAudio;
      for(let i=0;i<10;i++)a.dispatchEvent(new Event('timeupdate'));
      await Promise.resolve();observer.disconnect();return messages;
    });
    assert.deepEqual(announcements,[]);
    results.scenarios.push({name:'HTML-audio-play-pause-seek-speed-dialog',tickAnnouncements:announcements});
    // Enlarge actual text while keeping the phone viewport. The app uses px
    // fonts, so changing only the root font size would not test enlargement.
    await page.evaluate(()=>{
      const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
      for(const [element,size] of sizes) element.style.fontSize=`${size*2}px`;
    });
    await noOverflow(page);await page.screenshot({path:path.join(output,'after-phone-200-percent.png')});
    await page.setViewportSize({width:1280,height:800});
    await page.reload();await noOverflow(page);await axe(page,'Hebrew desktop search');
    for(const link of await page.locator('[data-show-card] .show-art').all()) {
      assert.equal(await link.getAttribute('aria-label'),await link.evaluate(e=>e.closest('[data-show-card]').dataset.showTitle));
    }
    await page.locator('[data-language-toggle]').click();
    assert.equal(await page.locator('html').getAttribute('dir'),'ltr');
    await noOverflow(page);await axe(page,'English desktop search');
    await page.screenshot({path:path.join(output,'after-desktop-english.png')});
    results.scenarios.push({name:'phone-200-percent-and-desktop-Hebrew-English'});
    // Browser Back still changes routes, independent of Escape behavior.
    await page.goBack();assert.equal(new URL(page.url()).pathname,'/');
    const android=await localContext({userAgent:'Mozilla/5.0 Android TorahPodAndroid/1 TorahPodVersion/0.5.0'});
    await android.addInitScript(()=>{
      localStorage.setItem('torahpod-native-audio-enabled','true');
      window.nativeCalls=[];
      window.prompt=(kind,json)=>{
        const call=JSON.parse(json);window.nativeCalls.push(call);
        if(call.command==='play')setTimeout(()=>window.TorahPodNativeProgress({position:30,duration:120,playing:true}),0);
        return '';
      };
    });
    const androidPage=await android.newPage();
    await androidPage.goto('http://local.test/');
    await androidPage.locator('[data-episode-play]').first().click();
    await androidPage.waitForFunction(()=>window.nativeCalls.some(c=>c.command==='play'));
    assert.match(await androidPage.locator('[data-player-seek]').getAttribute('aria-valuetext'),/0:30/);
    await androidPage.locator('[data-player-details]').click();
    assert.equal(await androidPage.evaluate(()=>window.TorahPodHandleBack()),true);
    assert.equal(await androidPage.locator('[data-player-details]').evaluate(e=>e===document.activeElement),true);
    await androidPage.locator('.episode-more summary').first().click();
    assert.equal(await androidPage.evaluate(()=>window.TorahPodHandleBack()),true);
    assert.equal(await androidPage.locator('.episode-more').first().evaluate(e=>e.open),false);
    results.scenarios.push({name:'Android-UA-and-stubbed-native-progress-Back',physicalAndroid:false});
    await android.close();
  }
  await context.close();
} finally {
  await writeFile(path.join(output,`${baseline?'before':'after'}-interactions.json`),JSON.stringify(results,null,2));
  await browser.close();
}
console.log(JSON.stringify(results,null,2));
