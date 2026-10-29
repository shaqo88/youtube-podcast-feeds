// Optional browser regression: node tests/text-reflow.browser.mjs
// CLI/environment: PLAYWRIGHT_MODULE, CHROMIUM_EXECUTABLE, REFLOW_BASELINE=1.
// All requests are local intercepted fixtures. No accounts or production writes.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
for(const arg of process.argv.slice(2)) {
  const match=arg.match(/^--([A-Z_]+)=(.*)$/);if(match)process.env[match[1]]=match[2];
}
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=process.cwd(),output=path.join(root,'tmp/text-reflow');
await mkdir(output,{recursive:true});
const baseline=process.env.REFLOW_BASELINE==='1';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const catalog=JSON.parse(await readFile('public/search-index.json','utf8')).episodes;
const longest=catalog.reduce((a,b)=>(a.title||'').length>(b.title||'').length?a:b);
const queued=catalog.slice(0,3).map((e,i)=>({id:e.id,src:'http://local.test/fixture.wav',href:'http://local.test/'+e.show_slug+'/',title:e.title,show:e.show,showSlug:e.show_slug,duration:3600}));
const wav=Buffer.alloc(44+960000);
wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);
wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);
wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(wav.length-44,40);
const report={baseline,browser:browser.version(),settings:{widths:[320,360,390],height:844,deviceScaleFactor:1,
  textScale:'snapshot all computed descendant font sizes, then multiply by 2; no cumulative inheritance multiplication',
  browserZoom:'not changed in the text matrix; separate pinch-style visual zoom experiment',longTitle:longest.title},cases:[],experiments:[]};
const csp=(await readFile('public/_headers','utf8')).match(/Content-Security-Policy:\s*(.+)/)?.[1];
async function contextFor(width,lang,height=844,options={}) {
  const context=await browser.newContext({viewport:{width,height},deviceScaleFactor:1,serviceWorkers:'block',reducedMotion:options.motion||'reduce'});
  await context.addInitScript(({lang,queued})=>{
    localStorage.setItem('torahpod-language',lang);
    localStorage.setItem('torahpod:v1:queue',JSON.stringify(queued));
    const scroll=window.scrollBy.bind(window);window.fixtureScrollCalls=[];
    window.scrollBy=(...args)=>{window.fixtureScrollCalls.push(args);return scroll(...args);};
  },{lang,queued});
  await context.route('**/*',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==='/fixture.wav'||route.request().resourceType()==='media')return route.fulfill({status:200,contentType:'audio/wav',body:wav});
    if(url.origin!=='http://local.test')return route.abort();
    try {
      let file=path.join(root,'public',decodeURIComponent(url.pathname));
      if((await stat(file)).isDirectory())file=path.join(file,'index.html');
      await route.fulfill({status:200,headers:options.csp&&path.extname(file)==='.html'?{'Content-Security-Policy':csp}:{},contentType:({'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css','.woff2':'font/woff2','.ttf':'font/ttf','.png':'image/png','.webp':'image/webp'})[path.extname(file)]||'application/octet-stream',body:await readFile(file)});
    }catch{await route.fulfill({status:404,body:'Missing local fixture'});}
  });
  return context;
}
async function enlarge(page,factor) {
  await page.evaluate(factor=>{
    // Reset earlier fixture sizes before measuring newly rendered menu/route
    // content, so inherited sizes are never multiplied twice.
    for(const e of window.fixtureSizedElements||[])e.style.removeProperty('font-size');
    const sizes=[...document.querySelectorAll('body *')].map(e=>[e,parseFloat(getComputedStyle(e).fontSize)]);
    for(const [element,size] of sizes)element.style.fontSize=`${size*factor}px`;
    window.fixtureSizedElements=sizes.map(([e])=>e);
  },factor);
  await page.waitForTimeout(120);
}
async function settle(page) {
  await page.evaluate(()=>document.fonts.ready);
  await page.waitForFunction(()=>{
    const s=getComputedStyle(document.documentElement),p=document.querySelector('[data-player]');
    return parseFloat(s.getPropertyValue('--mobile-nav-height'))===Math.ceil(document.querySelector('.app-bottom-nav').getBoundingClientRect().height)
      &&parseFloat(s.getPropertyValue('--mobile-player-height'))===(p.hidden||p.classList.contains('is-expanded')?0:Math.ceil(p.getBoundingClientRect().height));
  });
}
async function scaleSheetFonts(page,factor) {
  // An additional persistent text-only fixture for SPA navigation: scale
  // absolute/rem/vw CSS font sizes, leaving inherited em/% sizes relative.
  await page.evaluate(factor=>{
    const visit=rules=>{for(const rule of rules){
      if(rule.cssRules)visit(rule.cssRules);
      const size=rule.style?.fontSize;
      if(size&&size!=='inherit'&&size!=='initial'&&size!=='unset'&&!/(^|[^r])em\b|%/.test(size))rule.style.fontSize=`calc(${factor} * (${size}))`;
    }};
    for(const sheet of document.styleSheets)if(sheet.href?.startsWith(location.origin))visit(sheet.cssRules);
  },factor);
  await settle(page);
}
async function startPlayer(page) {
  if(await page.locator('[data-episode-id]').count())await page.locator('[data-episode-play]').first().click();
  else await page.locator('[data-queue-play]').first().click();
  await page.waitForFunction(()=>[...document.querySelectorAll('audio')].some(a=>!a.paused&&a.currentTime>0));
  await page.locator('[data-player-toggle]').click();
  await page.waitForTimeout(150);
  // Layout stress only: use the longest actual catalog title in the player.
  await page.locator('[data-player-title]').evaluate((e,title)=>{e.textContent=title;},longest.title);
}
async function geometry(page) {
  return page.evaluate(()=>{
    const rect=e=>{if(!e||!e.getClientRects().length)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right,bottom:r.bottom};};
    const labels=[...document.querySelectorAll('.bottom-nav-item')].map(e=>{
      const label=e.querySelector('[data-i18n]'),range=document.createRange();range.selectNodeContents(label);
      return {text:label.textContent,box:rect(e),textRects:[...range.getClientRects()].map(r=>({x:r.x,y:r.y,right:r.right,bottom:r.bottom})),font:parseFloat(getComputedStyle(label).fontSize)};
    });
    const flow=document.documentElement.classList.contains('mobile-chrome-flow'),expanded=!!document.querySelector('.is-expanded[data-player]');
    const targets=expanded||flow?[]:[...document.querySelectorAll('.bottom-nav-item,[data-player-toggle],[data-player-details],[data-player-open]')].filter(e=>e.getClientRects().length).map(e=>{
      const r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
      return {name:e.getAttribute('aria-label')||e.textContent.trim().slice(0,24),w:r.width,h:r.height,hit:!!hit&&(hit===e||e.contains(hit))};
    });
    const textOutside=[];
    for(const e of document.querySelectorAll('main h1,main h2,main h3')){
      if(!e.getClientRects().length)continue;
      const range=document.createRange();range.selectNodeContents(e);
      if([...range.getClientRects()].some(r=>r.x<-.5||r.right>innerWidth+.5))textOutside.push(e.textContent.slice(0,60));
    }
    const controlTextOutside=[];
    for(const e of document.querySelectorAll('button:not([data-player-open]),.bottom-nav-item')) {
      if(!e.getClientRects().length)continue;
      const box=e.getBoundingClientRect(),walker=document.createTreeWalker(e,NodeFilter.SHOW_TEXT);
      let text;while(text=walker.nextNode()){
        if(!text.textContent.trim()||text.parentElement.closest('.sr-only,svg,[aria-hidden=true]'))continue;
        const range=document.createRange();range.selectNodeContents(text);
        if([...range.getClientRects()].some(r=>r.x<box.x-.5||r.right>box.right+.5||r.y<box.y-.5||r.bottom>box.bottom+.5))controlTextOutside.push(text.textContent.slice(0,40));
      }
    }
    const title=document.querySelector('[data-player-open]');
    return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,visualScale:visualViewport.scale,
      header:rect(document.querySelector('.site-header')),nav:rect(document.querySelector('.app-bottom-nav')),
      player:rect(document.querySelector('[data-player]')),expanded:!!document.querySelector('.is-expanded[data-player]'),
      flow:document.documentElement.classList.contains('mobile-chrome-flow'),
      headerControls:[...document.querySelectorAll('.brand,.account-toggle,.nav-menu-toggle,.nav-search-shortcut')].map(e=>({name:e.getAttribute('aria-label')||e.textContent,box:rect(e)})).filter(x=>x.box),
      playerToggle:rect(document.querySelector('[data-player-toggle]')),labels,
      targets,textOutside,controlTextOutside,titleOverflow:getComputedStyle(title).overflowY,titleLength:title.textContent.length,
      padding:parseFloat(getComputedStyle(document.body).paddingBottom)};
  });
}
function problems(g) {
  const issues=[];
  if(g.scrollWidth>g.width+1)issues.push('horizontal-page-overflow');
  if(g.textOutside.length)issues.push('heading-text-outside-viewport');
  if(g.controlTextOutside.length)issues.push('control-text-outside-target');
  if(g.targets.some(t=>!t.hit||t.w<44||t.h<44))issues.push('essential-touch-target-covered-or-small');
  if(g.titleOverflow!=='auto')issues.push('long-title-not-contained-in-scroll-region');
  for(const c of g.headerControls)if(c.box.x<-.5||c.box.right>g.width+.5)issues.push('header-control-clipped');
  for(const l of g.labels)for(const r of l.textRects)if(r.x<l.box.x-.5||r.right>l.box.right+.5||r.bottom>l.box.bottom+.5)issues.push('navigation-label-outside-target');
  if(g.player&&!g.expanded&&!g.flow&&g.player.bottom>g.nav.y-3)issues.push('player-overlaps-navigation');
  if(g.player&&!g.expanded&&!g.flow&&g.player.y<g.header.bottom)issues.push('player-overlaps-header');
  return [...new Set(issues)];
}
async function focusVisible(page,selector,expanded=false) {
  const element=page.locator(selector).last();
  await element.focus();await page.waitForTimeout(50);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  return element.evaluate((e,expanded)=>{
    const r=e.getBoundingClientRect(),header=document.querySelector('.site-header').getBoundingClientRect();
    const player=document.querySelector('[data-player]'),nav=document.querySelector('.app-bottom-nav').getBoundingClientRect();
    const flow=document.documentElement.classList.contains('mobile-chrome-flow');
    const top=expanded?player.getBoundingClientRect().top:flow?0:header.bottom;
    const bottom=expanded?player.getBoundingClientRect().bottom:flow?innerHeight:Math.min(nav.top,player.hidden?Infinity:player.getBoundingClientRect().top);
    const style=getComputedStyle(e);
    return {rect:{x:r.x,y:r.y,right:r.right,bottom:r.bottom},top,bottom,outline:style.outlineStyle,
      hit:e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)),
      scrollCalls:window.fixtureScrollCalls,scrollY,maxScroll:document.documentElement.scrollHeight-innerHeight,
      visible:r.left>=0&&r.right<=innerWidth&&r.top>=top-1&&r.bottom<=bottom+1};
  },expanded);
}
async function menuCase(page,selector,trigger,factor) {
  await page.locator(trigger).first().click();if(factor===2)await enlarge(page,2);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const menu=page.locator(selector).first();
  const bounds=await menu.evaluate(e=>{
    const r=e.getBoundingClientRect(),h=document.querySelector('.site-header').getBoundingClientRect();
    const p=document.querySelector('[data-player]').getBoundingClientRect();
    const ancestors=[];for(let a=e.parentElement;a;a=a.parentElement){const s=getComputedStyle(a);if(s.transform!=='none'||s.contain!=='none'||s.contentVisibility!=='visible')ancestors.push({tag:a.tagName,classes:a.className,transform:s.transform,contain:s.contain,contentVisibility:s.contentVisibility});}
    return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,headerBottom:h.bottom,playerTop:p.top,scrollHeight:e.scrollHeight,height:e.clientHeight,position:getComputedStyle(e).position,top:getComputedStyle(e).top,left:getComputedStyle(e).left,rootHeader:getComputedStyle(document.documentElement).getPropertyValue('--mobile-header-height'),ancestors};
  });
  await menu.locator('a,button,select').last().focus();
  const lastVisible=await menu.locator('a,button,select').last().evaluate(e=>{
    const r=e.getBoundingClientRect(),m=e.closest('.nav-overflow-menu,.account-menu,.episode-more-menu').getBoundingClientRect();
    return r.top>=m.top&&r.bottom<=m.bottom&&r.right<=innerWidth&&r.left>=0;
  });
  await page.keyboard.press('Escape');
  return {bounds,lastVisible};
}
try {
  if(baseline)for(const width of [320,360,390])for(const lang of ['he','en']) {
    const context=await contextFor(width,lang),page=await context.newPage();page.setDefaultTimeout(10000);
    await page.goto('http://local.test/');await page.locator('[data-episode-play]').first().waitFor();
    await page.waitForTimeout(200);await startPlayer(page);await enlarge(page,2);
    const g=await geometry(page),issues=problems(g),name=`${lang}-${width}-home-2x`;
    report.cases.push({name,geometry:g,issues});
    await page.screenshot({path:path.join(output,`${baseline?'before':'after'}-${name}.png`)});
    if(!baseline)assert.deepEqual(issues,[],name);
    await context.close();
  }
  else if(process.env.REFLOW_EXPERIMENTS_ONLY!=='1')for(const width of (process.env.REFLOW_WIDTH?[Number(process.env.REFLOW_WIDTH)]:[320,360,390]))for(const lang of (process.env.REFLOW_LANG?[process.env.REFLOW_LANG]:['he','en']))for(const factor of [1,2]) {
    const context=await contextFor(width,lang),page=await context.newPage();page.setDefaultTimeout(10000);
    for(const view of (process.env.REFLOW_VIEW?[process.env.REFLOW_VIEW]:['home','search','show','queue','player'])) {
      const route=view==='search'?'search/':view==='show'?catalog[0].show_slug+'/':view==='queue'?'queue/':'';
      await page.goto('http://local.test/'+route);await page.waitForTimeout(200);
      await page.evaluate(()=>document.fonts.ready);
      await startPlayer(page);
      if(view==='player')await page.locator('[data-player-open]').click();
      if(factor===2)await enlarge(page,2);else await page.waitForTimeout(120);
      await settle(page);
      const g=await geometry(page),issues=problems(g),name=`${lang}-${width}-${view}-${factor}x`;
      const result={name,geometry:g,issues};report.cases.push(result);
      await page.screenshot({path:path.join(output,`after-${name}.png`)});
      assert.deepEqual(issues,[],name);
      assert.equal(g.visualScale,1);
      assert.equal(g.labels[0].font,11*factor,`${name}: exact text multiplier`);
      if(view!=='player') {
        assert.ok(g.flow||g.padding>=g.nav.h+g.player.h+8,'body reserves actual dock height');
        result.focus=await focusVisible(page,'main button:not([disabled]):visible,main a[href]:visible');
        assert.ok(result.focus.visible,`${name}: main focus behind fixed chrome: ${JSON.stringify(result.focus)}`);
      } else {
        result.playFocus=await focusVisible(page,'[data-player-toggle]',true);
        assert.ok(result.playFocus.visible,`${name}: full player playback control reachable`);
        await page.locator('[data-player-open]').focus();await page.keyboard.press('PageDown');await page.waitForTimeout(200);
        result.titleScroll=await page.locator('[data-player-open]').evaluate(e=>e.scrollTop);
        assert.ok(result.titleScroll>0,`${name}: expanded long title keyboard scroll`);
        result.focus=await focusVisible(page,'[data-player-speed]',true);
        assert.ok(result.focus.visible,`${name}: full player focus`);
        result.stopFocus=await focusVisible(page,'[data-player-close]',true);
        assert.ok(result.stopFocus.visible&&result.stopFocus.hit,`${name}: stop control reachable`);
        result.volumeFocus=await focusVisible(page,'.player-volume',true);
        assert.ok(result.volumeFocus.visible&&result.volumeFocus.hit,`${name}: volume control reachable`);
        await page.screenshot({path:path.join(output,`after-${name}-controls.png`)});
        await page.keyboard.press('Escape');
      }
      if(view==='home') {
        result.headerMenu=await menuCase(page,'.nav-overflow-menu','[data-nav-menu-toggle]',factor);
        assert.ok(result.headerMenu.lastVisible,`${name}: header menu last control`);
        const b=result.headerMenu.bounds;
        assert.ok(b.x>=0&&b.right<=width&&b.y>=b.headerBottom&&b.bottom<=b.playerTop,`${name}: header menu bounds`);
        result.accountMenu=await menuCase(page,'.account-menu','[data-account-toggle]',factor);
        assert.ok(result.accountMenu.lastVisible,`${name}: account menu last control`);
        result.episodeMenu=await menuCase(page,'.episode-more-menu','.episode-more summary',factor);
        assert.ok(result.episodeMenu.lastVisible,`${name}: episode menu last control`);
        const e=result.episodeMenu.bounds;
        assert.ok(e.x>=0&&e.right<=width&&e.y>=e.headerBottom&&e.bottom<=e.playerTop,`${name}: episode menu bounds: ${JSON.stringify(e)}`);
      }
    }
    await context.close();
  }
  if(!baseline&&!process.env.REFLOW_VIEW) {
    for(const [width,height] of [[320,568],[360,640],[390,640]])for(const lang of ['he','en'])for(const factor of [1,2]) {
      const context=await contextFor(width,lang,height),page=await context.newPage();page.setDefaultTimeout(10000);
      await page.goto('http://local.test/');await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(200);await startPlayer(page);
      if(factor===2)await enlarge(page,2);await settle(page);
      const g=await geometry(page),name=`${lang}-${width}x${height}-home-${factor}x`,issues=problems(g);
      report.cases.push({name,geometry:g,issues});assert.deepEqual(issues,[],name);
      if(factor===1)assert.equal(g.flow,false,`${name}: normal-size fixed layout retained`);
      if(g.flow) {
        const order=await page.evaluate(()=>{
          const children=[...document.body.children];return ['.site-header','.app-bottom-nav','[data-player]','main'].map(s=>children.indexOf(document.querySelector(s)));
        });
        assert.deepEqual([...order].sort((a,b)=>a-b),order,'flow DOM order matches visual/keyboard order');
        await page.locator('[data-nav-menu-toggle]').focus();
        for(let i=0;i<5;i++) {
          await page.keyboard.press('Tab');
          assert.equal(await page.evaluate(()=>!!document.activeElement.closest('.app-bottom-nav')),true,'Tab visits navigation in document order');
          const target=await page.evaluate(()=>{const r=document.activeElement.getBoundingClientRect();return {y:r.y,bottom:r.bottom,w:r.width,h:r.height,outline:getComputedStyle(document.activeElement).outlineStyle};});
          assert.ok(target.y>=0&&target.bottom<=height&&target.w>=44&&target.h>=44&&target.outline!=='none','short-screen keyboard target reachable');
        }
      }
      await page.screenshot({path:path.join(output,`after-${name}.png`)});
      await page.locator('[data-player-open]').focus();await page.keyboard.press('PageDown');await page.waitForTimeout(200);
      const title=await page.locator('[data-player-open]').evaluate(e=>({scroll:e.scrollTop,total:e.scrollHeight,visible:e.clientHeight,text:e.textContent,overflow:getComputedStyle(e).overflowY}));
      assert.ok(title.scroll>0&&title.total>title.visible&&title.overflow==='auto','long title is keyboard-scrollable');
      report.experiments.push({name:name+'-title-scroll',title});
      await context.close();
    }
    for(const lang of ['he','en']) {
      const context=await contextFor(390,lang,844,{csp:true,motion:'no-preference'}),page=await context.newPage();page.setDefaultTimeout(10000);
      await page.goto('http://local.test/');await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(800);await startPlayer(page);await scaleSheetFonts(page,2);
      const initial=await geometry(page);assert.deepEqual(problems(initial),[]);
      const menu=await menuCase(page,'.episode-more-menu','.episode-more summary',1);
      assert.ok(menu.lastVisible&&menu.bounds.bottom<=menu.bounds.playerTop,'CSP/normal-motion episode menu');
      await page.setViewportSize({width:320,height:568});await settle(page);
      const short=await geometry(page);assert.equal(short.flow,true);assert.deepEqual(problems(short),[]);
      await page.setViewportSize({width:390,height:844});await settle(page);
      const restored=await geometry(page);assert.equal(restored.flow,false);assert.equal(restored.labels[0].font,22);assert.deepEqual(problems(restored),[]);
      report.experiments.push({name:lang+'-resize-and-production-CSP',initial,short,restored});
      await page.evaluate(()=>scrollTo(0,500));
      const saved=await page.evaluate(()=>scrollY);
      await page.locator('.app-bottom-nav a[data-app-route="/search/"]').evaluate(e=>e.click());await page.waitForURL('**/search/');
      await page.goBack();await page.waitForURL('http://local.test/');await page.waitForTimeout(300);
      const back=await page.evaluate(()=>scrollY);assert.ok(Math.abs(back-saved)<=2,'Back restores the window scroll position');
      report.experiments.push({name:lang+'-back-scroll',saved,back});
      await context.close();
    }
    const context=await contextFor(390,'en'),page=await context.newPage();await page.goto('http://local.test/');await page.evaluate(()=>document.fonts.ready);
    const readZoom=()=>page.evaluate(()=>({layoutWidth:innerWidth,visualWidth:visualViewport.width,visualScale:visualViewport.scale,font:parseFloat(getComputedStyle(document.querySelector('.bottom-nav-item')).fontSize),dpr:devicePixelRatio}));
    const before=await readZoom(),cdp=await context.newCDPSession(page);await cdp.send('Emulation.setPageScaleFactor',{pageScaleFactor:2});
    const after=await readZoom();assert.equal(after.layoutWidth,before.layoutWidth);assert.equal(after.font,before.font);assert.equal(after.visualScale,2);
    report.experiments.push({name:'pinch-style-visual-zoom-only',before,after,establishes:'Visual magnification changes the visual viewport; it is not text-only scaling or desktop browser UI zoom.'});
    await context.close();
  }
}finally {
  await writeFile(path.join(output,`${baseline?'before':'after'}-matrix.json`),JSON.stringify(report,null,2));
  await browser.close();
}
console.log(JSON.stringify({cases:report.cases.length,issues:report.cases.map(c=>({name:c.name,issues:c.issues}))},null,2));
