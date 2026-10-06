(() => {
  'use strict';
  const script=document.currentScript;
  const base=new URL('../',script.src);
  let controller=null,loading=null,config=null;
  async function start() {
    config ||= await fetch(new URL('accounts-config.json',base),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error();return r.json();});
    if(!config.listenerAccounts&&!config.publisherAccess) {
      const page=document.querySelector('[data-account-page]');
      if(page)page.querySelector('[data-account-content]').textContent=document.documentElement.lang==='he'
        ?'חשבונות יהיו זמינים בקרוב. אפשר להמשיך להאזין ולשמור במכשיר הזה.'
        :'Accounts will be available soon. You can keep listening and saving on this device.';
      return;
    }
    loading ||= import(new URL('assets/accounts.js',base)).then(module=>module.initialize(config,base));
    controller=await loading;controller.render();
  }
  function onRoute() {
    if(controller)return controller.render();
    let returning=false;try{returning=localStorage.getItem('torahpod-account-session')==='true';}catch{}
    if(document.querySelector('[data-account-page]')||returning)start().catch(()=>{
      const content=document.querySelector('[data-account-content]');
      if(content){
        content.textContent=document.documentElement.lang==='he'?'לא ניתן לפתוח חשבון כרגע. ':'Account is unavailable. ';
        const retry=document.createElement('button');retry.className='button';retry.type='button';
        retry.textContent=document.documentElement.lang==='he'?'ניסיון נוסף':'Try again';retry.addEventListener('click',onRoute);content.append(retry);
      }
      loading=null;
    });
  }
  document.addEventListener('torahpod:navigation',onRoute);
  document.addEventListener('torahpod:languagechange',()=>controller?controller.render():onRoute());
  onRoute();
})();
