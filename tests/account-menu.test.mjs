import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import test from 'node:test';

function fixture(fetchConfig) {
  const events=new Map(),attributes={},menu={hidden:true},content={children:[],replaceChildren(...nodes){this.children=nodes;},append(node){this.children.push(node);}};
  let focused=false;
  const toggle={setAttribute(key,value){attributes[key]=value;},focus(){focused=true;}};
  const document={currentScript:{src:'https://example.test/assets/accounts-bootstrap.js'},documentElement:{lang:'en'},
    querySelector(selector){if(selector==='[data-account-menu]:not([hidden])')return menu.hidden?null:menu;return {'[data-account-toggle]':toggle,'[data-account-menu]':menu,'[data-account-menu-content]':content}[selector]||null;},
    createElement(){return {dataset:{},setAttribute(){}};},
    addEventListener(type,callback){events.set(type,callback);}};
  runInNewContext(readFileSync('podcast_feeds/web/accounts-bootstrap.js','utf8'),{document,URL,localStorage:{getItem:()=>null},fetch:fetchConfig});
  const click=kind=>events.get('click')({target:{closest(selector){return (kind==='toggle'&&selector==='[data-account-toggle]')?toggle:(kind==='retry'&&selector==='[data-account-load]')?{}:null;}}});
  return {menu,content,attributes,click,events,get focused(){return focused;}};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('account circle loads lazily, closes outside and Escape restores focus',async()=>{
  let requests=0;
  const ui=fixture(async()=>{requests++;return {ok:true,json:async()=>({listenerAccounts:false,publisherAccess:false})};});
  assert.equal(requests,0);ui.click('toggle');await tick();
  assert.equal(requests,1);assert.equal(ui.menu.hidden,false);assert.equal(ui.attributes['aria-expanded'],'true');
  assert.match(ui.content.children[0].textContent,/available soon/);
  let stopped=false;
  ui.events.get('keydown')({key:'Escape',preventDefault(){},stopImmediatePropagation(){stopped=true;}});
  assert.equal(ui.menu.hidden,true);assert.equal(ui.focused,true);assert.equal(stopped,true);
  ui.click('toggle');await tick();ui.click('outside');assert.equal(ui.menu.hidden,true);
  assert.equal(requests,1);
  ui.click('toggle');await tick();ui.events.get('torahpod:closeaccountmenu')();assert.equal(ui.menu.hidden,true);
});
test('an offline header retains navigation and can retry loading without a page reload',async()=>{
  let offline=true;
  const ui=fixture(async()=>{if(offline)throw new Error('offline');return {ok:true,json:async()=>({listenerAccounts:false,publisherAccess:false})};});
  ui.click('toggle');await tick();assert.match(ui.content.children[0].textContent,/unavailable/);
  assert.equal(ui.content.children[1].dataset.accountLoad,'true');assert.equal(ui.menu.hidden,false);
  offline=false;ui.click('retry');await tick();assert.match(ui.content.children[0].textContent,/available soon/);
});
