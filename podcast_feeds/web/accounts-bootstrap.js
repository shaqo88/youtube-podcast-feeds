(() => {
  'use strict';
  const script=document.currentScript;
  const base=new URL('../',script.src);
  let controller=null,loading=null,config=null;
  const phrase=(en,he)=>document.documentElement.lang==='he'?he:en;
  function menuMessage(message,retry=false) {
    const content=document.querySelector('[data-account-menu-content]');if(!content)return;
    const text=document.createElement('p');text.setAttribute('role','status');text.textContent=message;
    content.replaceChildren(text);
    if(retry){const button=document.createElement('button');button.type='button';button.dataset.accountLoad='true';button.textContent=phrase('Try again','ניסיון נוסף');content.append(button);}
  }
  function closeMenu(restoreFocus=false) {
    const toggle=document.querySelector('[data-account-toggle]');
    const menu=document.querySelector('[data-account-menu]');if(!menu||menu.hidden)return;
    menu.hidden=true;toggle?.setAttribute('aria-expanded','false');if(restoreFocus)toggle?.focus();
  }
  async function start() {
    config ||= await fetch(new URL('accounts-config.json',base),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json();});
    if(!config.listenerAccounts&&!config.publisherAccess) {
      const page=document.querySelector('[data-account-page]');
      if(page)page.querySelector('[data-account-content]').textContent=document.documentElement.lang==='he'
        ?'חשבונות יהיו זמינים בקרוב. אפשר להמשיך להאזין ולשמור במכשיר הזה.'
        :'Accounts will be available soon. You can keep listening and saving on this device.';
      menuMessage(phrase('Accounts will be available soon.','חשבונות יהיו זמינים בקרוב.'));
      return;
    }
    loading ||= import(new URL('assets/accounts.js',base)).then(module=>module.initialize(config,base));
    controller=await loading;controller.render();
  }
  function load() {
    if(controller){controller.render();return;}
    menuMessage(phrase('Connecting…','מתחבר…'));
    return start().catch(()=>{
      menuMessage(phrase('Account is unavailable.','לא ניתן לפתוח חשבון כרגע.'),true);
      const content=document.querySelector('[data-account-content]');
      if(content){
        content.textContent=phrase('Account is unavailable. ','לא ניתן לפתוח חשבון כרגע. ');
      }
      loading=null;
    });
  }
  function onRoute() {
    if(controller)return controller.render();
    let returning=false;try{returning=localStorage.getItem('torahpod-account-session')==='true';}catch{}
    if(document.querySelector('[data-account-page]')||returning||document.querySelector('[data-account-menu]:not([hidden])'))load();
  }
  document.addEventListener('click',event=>{
    const toggle=event.target.closest?.('[data-account-toggle]');
    if(toggle){
      const menu=document.querySelector('[data-account-menu]');if(!menu)return;
      menu.hidden=!menu.hidden;toggle.setAttribute('aria-expanded',String(!menu.hidden));
      if(!menu.hidden)load();return;
    }
    if(event.target.closest?.('[data-account-load]')){load();return;}
    if(!event.target.closest?.('[data-account-nav]')||event.target.closest?.('a'))closeMenu();
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&document.querySelector('[data-account-menu]:not([hidden])')) {
      event.preventDefault();event.stopImmediatePropagation();closeMenu(true);
    }
  },true);
  document.addEventListener('torahpod:closeaccountmenu',()=>closeMenu(true));
  document.addEventListener('torahpod:navigation',()=>{closeMenu();onRoute();});
  document.addEventListener('torahpod:languagechange',()=>controller?controller.render():onRoute());
  onRoute();
})();
