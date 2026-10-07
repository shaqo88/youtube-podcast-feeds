import {AccountStore,openStore} from './accounts-core.mjs';

const phrases={
  title:['Account','חשבון'],google:['Continue with Google','כניסה באמצעות Google'],retry:['Try again','ניסיון נוסף'],
  yourAccount:['Your account','החשבון שלך'],syncListening:['Sync your listening','סנכרון ההאזנה שלך'],signedIn:['Signed in with Google','מחובר עם Google'],
  explain:['Sign in to synchronize follows, saved episodes and listening progress across devices. Your queue and player settings stay on this device.','כניסה לחשבון מסנכרנת מינויים, פרקים שמורים והתקדמות האזנה בין מכשירים. התור והגדרות הנגן נשארים במכשיר הזה.'],
  export:['Export my data','ייצוא הנתונים שלי'],signout:['Sign out','יציאה מהחשבון'],delete:['Delete account','מחיקת חשבון'],
  deletion:['Delete your Google-linked Torah Pod account and listening data? Public shows stay published. Private publication-rights records may be retained separately.','למחוק את חשבון Torah Pod ונתוני ההאזנה? פודקאסטים ציבוריים יישארו זמינים. רישומי הרשאות לפרסום עשויים להישמר בנפרד.'],
  cancel:['Cancel','ביטול'],confirmDelete:['Delete my account','מחיקת החשבון שלי'],
  pending:['Waiting to synchronize','ממתין לסנכרון'],synced:['Up to date','הנתונים מסונכרנים'],offline:['Changes saved on this device; waiting for a connection.','השינויים נשמרו במכשיר; ממתינים לחיבור.'],
  connecting:['Connecting…','מתחבר…'],reauthentication:['Sign in again to deliver your saved changes.','היכנסו שוב כדי לשלוח את השינויים השמורים.'],
  failure:['Could not complete this action. Your player is still available. Please try again.','לא ניתן להשלים את הפעולה. הנגן עדיין זמין. נסו שוב.'],
  authFailure:['Sign-in was canceled or the popup could not open. Please try again.','הכניסה בוטלה או שהחלון לא נפתח. נסו שוב.'],
  oldWrapper:['Update Torah Pod from Google Play to use accounts. Anonymous listening remains available.','עדכנו את Torah Pod דרך Google Play כדי להשתמש בחשבונות. אפשר להמשיך להאזין ללא חשבון.'],
  import:['Import this device’s listening data','ייבוא נתוני ההאזנה מהמכשיר הזה'],separate:['Keep it separate','שמירה בנפרד'],
  preview:['You can import follows, saved episodes and progress. Existing cloud removals stay removed; equal or unknown update times keep cloud progress. Your guest data remains separate.','אפשר לייבא מינויים, פרקים שמורים והתקדמות. מחיקות מהענן נשמרות; זמן עדכון זהה או לא ידוע שומר על ההתקדמות בענן. נתוני האורח נשארים בנפרד.'],
  discard:['Offline changes remain. Signing out now discards them from this device.','נותרו שינויים שלא סונכרנו. יציאה עכשיו תמחק אותם מהמכשיר הזה.'],
  stay:['Stay signed in','להישאר בחשבון'],discardSignout:['Discard changes and sign out','מחיקת השינויים ויציאה'],
  conflict:['Another device changed this item. Choose which change to keep.','מכשיר אחר שינה את הפריט הזה. בחרו איזה שינוי לשמור.'],
  devicePosition:['Keep this device’s position','שמירת המיקום במכשיר הזה'],cloudPosition:['Use cloud position','שימוש במיקום מהענן'],
  deviceChange:['Keep this device’s change','שמירת השינוי במכשיר הזה'],cloudChange:['Use cloud change','שימוש בשינוי מהענן'],
  publisher:['Publisher','מפרסם'],shows:['My Shows','הפודקאסטים שלי'],submit:['Submit Podcast','צירוף פודקאסט'],claim:['Claim Existing Show','בקשת שיוך פודקאסט קיים'],requests:['My Requests','הבקשות שלי'],
  rights:['I own this content or have authorization to publish it.','אני בעל התוכן או מורשה לפרסם אותו.'],
  manual:['An owner reviews every request. For a claim, place the one-time challenge on your original feed, source or website. Email matching does not grant ownership.','כל בקשה נבדקת ידנית. לשיוך פודקאסט, פרסמו את קוד האימות החד־פעמי במקור, בפיד או באתר שלכם. כתובת דוא״ל זהה אינה מעניקה בעלות.'],
  noShows:['No verified shows yet.','אין עדיין פודקאסטים מאומתים.'],noRequests:['No requests yet.','אין עדיין בקשות.'],
  submitted:['Submitted','נשלחה'],under_review:['Under review','בבדיקה'],needs_information:['Needs information','נדרש מידע נוסף'],approved:['Approved','אושרה'],published:['Published','פורסמה'],declined:['Declined','נדחתה'],
  send:['Send request','שליחת בקשה'],source:['Source','מקור'],sourceUrl:['Source or feed URL','כתובת מקור או פיד'],showSlug:['Show URL name','שם הפודקאסט בכתובת'],
  podcastTitle:['Podcast title','שם הפודקאסט'],speaker:['Speaker','שם הרב / הדובר'],startDate:['First episode date','תאריך הפרק הראשון'],
  contact:['Contact email (private)','דוא״ל ליצירת קשר (פרטי)'],notes:['Notes or authorization details (private)','הערות או פרטי הרשאה (פרטיים)'],proofUrl:['Original source or website for verification','מקור או אתר לצורך אימות'],
  requestPending:['This request is awaiting confirmation. Retry with the same details; My Requests shows its status.','הבקשה ממתינה לאישור קבלה. נסו שוב עם אותם הפרטים; אפשר לעקוב בבקשות שלי.'],
  followCount:['Follows','מינויים'],savedCount:['Saved episodes','פרקים שמורים'],progressCount:['Listening records','רשומות האזנה'],
};
const t=key=>phrases[key]?.[document.documentElement.lang==='he'?1:0]||key;
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const button=(key,action,extra='')=>`<button type="button" class="button secondary" data-account-action="${action}" ${extra}>${t(key)}</button>`;

export function nativeAuth() {
  const pending=new Map();let callback=()=>{};
  const call=(command,payload={})=>new Promise((resolve,reject)=>{
    const requestId=crypto.randomUUID();
    const timer=setTimeout(()=>{pending.delete(requestId);reject(new Error('native_auth_timeout'));},60000);
    pending.set(requestId,{resolve,reject,timer});
    try { window.prompt('torahpod-native',JSON.stringify({version:1,command,payload:{...payload,requestId}})); }
    catch(error){clearTimeout(timer);pending.delete(requestId);reject(error);}
  });
  window.TorahPodAuthResult=result=>{
    if(result.event==='authState'){callback(result.user);return;}
    const request=pending.get(result.requestId);if(!request)return;
    clearTimeout(request.timer);pending.delete(result.requestId);
    if(result.error)request.reject(new Error(result.error));else request.resolve(result);
  };
  let user=null;
  return {subscribe(fn){callback=value=>{user=value;fn(value);};call('authState').then(result=>callback(result.user)).catch(()=>callback(null));},
    current:()=>user,signIn:()=>call('authSignIn'),signOut:()=>call('authSignOut'),
    reauthenticate:()=>call('authSignIn',{reauthenticate:true}),token:(force,uid)=>call('authToken',{forceRefresh:force===true,uid}).then(r=>{if(r.uid!==uid)throw new Error('account_changed');return r.token;})};
}

export async function initialize(config,base) {
  if(!['preview','production'].includes(config.environment)||!config.apiOrigin||!config.firebase)throw new Error('configuration_unavailable');
  const api=new URL(config.apiOrigin);
  if(api.protocol!=='https:'||api.pathname!=='/'||api.search||api.hash)throw new Error('configuration_unavailable');
  let auth=null,store=null,user=null,problem='',mode='',publisher=null,publisherView='shows',switching=Promise.resolve(),deleted=false;
  let renderedLanguage='',publisherAttempt=null,destroyPublisherWidget=()=>{};
  let renderedMenu=null,renderedMenuBody='';
  const android=navigator.userAgent.includes('TorahPodAndroid/1');
  let oldWrapper=false;
  if(android) {
    let capability={};try{capability=JSON.parse(window.prompt('torahpod-native',JSON.stringify({version:1,command:'authCapabilities',payload:{}}))||'{}');}catch{}
    oldWrapper=capability.googleSignIn!==true||capability.environment!==config.environment;
    if(!oldWrapper)auth=nativeAuth();
  } else {
    const sdk=await import('./firebase-auth.bundle.js');auth=sdk.createAuth(config.firebase);
  }
  const db=auth?await openStore(config.environment):null;
  let hydrationKey='',hydrating=false;
  function emit(){document.dispatchEvent(new CustomEvent('torahpod:storagechange'));render();if(store&&!hydrating)void hydrate(store).catch(()=>{});}
  async function request(path,options={}) {
    const target=user?.uid;if(!target)throw Object.assign(new Error('authentication_required'),{status:401});
    let response;
    for(let attempt=0;attempt<2;attempt++) {
      const token=await auth.token(attempt===1,target);
      if(!token||user?.uid!==target||auth.current()?.uid!==target)throw Object.assign(new Error('authentication_required'),{status:401});
      response=await fetch(new URL(`/api/v1${path}`,api),{method:options.method||'GET',cache:'no-store',credentials:'omit',
        headers:{Authorization:`Bearer ${token}`,...(options.body?{'Content-Type':'application/json'}:{})},
        body:options.body?JSON.stringify(options.body):undefined,signal:AbortSignal.timeout(20000)});
      if(response.status!==401||attempt===1)break;
      const reason=await response.clone().json().catch(()=>({}));
      if(['account_deleted','account_unavailable'].includes(reason.error))break;
    }
    const body=await response.json();
    if(!response.ok)throw Object.assign(new Error(body.error),{status:response.status,body});
    return body;
  }
  async function hydrate(target) {
    const missing=Object.keys(target.session.records).filter(key=>!target.session.metadata[key]);
    const key=`${target.uid}:${missing.join(',')}`;
    if(!missing.length||key===hydrationKey)return;
    hydrationKey=key;hydrating=true;
    try {
    const catalogue=await fetch(new URL('catalog.json',base)).then(r=>r.json());
    let index=null;
    const keys=Object.keys(target.session.records);
    if(keys.some(key=>!key.startsWith('follows:')&&!target.session.metadata[key]))index=await fetch(new URL('search-index.json',base)).then(r=>r.json());
    const episodes=new Map((index?.episodes||[]).map(e=>[e.id,e]));
    if(!target.active)return;
    await target.update(s=>{
      for(const [key,record] of Object.entries(s.records)) {
        if(s.metadata[key])continue;
        const show=catalogue.find(item=>item.slug===(record.kind==='follows'?record.id:record.id.split(':')[0]));
        if(!show)continue;
        if(record.kind==='follows')s.metadata[key]={slug:show.slug,title:show.title,author:show.author,artwork:show.artwork_url,url:new URL(`${show.slug}/`,base).href};
        else {
          const ep=episodes.get(record.id);if(!ep)continue;
          s.metadata[key]={id:ep.id,title:ep.title,show:show.title,showSlug:ep.show_slug,artwork:show.artwork_url,
            src:ep.audio_url,href:new URL(ep.page_url,base).href,duration:ep.duration};
        }
      }
      return s;
    });
    } catch(error){hydrationKey='';throw error;} finally {hydrating=false;}
  }
  async function changed(next) {
    if(user?.uid===next?.uid)return;
    if(store){await store.stop(!next);store=null;}
    window.TorahPodStorage.activate(null);user=next;publisher=null;mode='';problem='';
    publisherAttempt=null;
    try{if(next)localStorage.setItem('torahpod-account-session','true');else localStorage.removeItem('torahpod-account-session');}catch{}
    if(next) {
      const target=new AccountStore({environment:config.environment,uid:next.uid,db,request,
        onChange:emit,onStatus(status){
          render();if(status==='deleted')void removeDeleted();
        }});
      store=target;
      try {
        const profile=await request('/me');
        if(profile.uid!==next.uid)throw new Error('authentication_required');
        if(!config.listenerAccounts){store=null;target.active=false;await loadPublisher();render();return;}
        await target.start();window.TorahPodStorage.activate(target);await hydrate(target);
        if(config.publisherAccess)await loadPublisher();
      } catch(error){
        if(error.body?.error==='account_deleted'){await removeDeleted();return;}
        if(!config.listenerAccounts){store=null;target.active=false;problem=t('failure');render();return;}
        // Restore an existing offline account cache without mixing in guest
        // state. Mutations stay namespaced to the identity that created them.
        await target.update(s=>s);window.TorahPodStorage.activate(target);target.setStatus('offline');target.schedule();
      }
    }
    render();
  }
  async function removeDeleted() {
    if(deleted)return;deleted=true;
    if(store){await store.stop(true);store=null;}window.TorahPodStorage.activate(null);
    user=null;await auth.signOut();deleted=false;render();
    try{localStorage.removeItem('torahpod-account-session');}catch{}
  }
  async function signout(discard=false) {
    const target=store;
    if(target&&!discard){await target.flush(true);if(target.session.outbox.length||target.session.importJob){mode='signout';render();return;}}
    if(target)await target.stop(true);
    store=null;window.TorahPodStorage.activate(null);await auth.signOut();user=null;mode='';render();
    try{localStorage.removeItem('torahpod-account-session');}catch{}
  }
  async function loadPublisher() {
    const [shows,first]=await Promise.all([request('/publisher/shows'),request('/publisher/requests')]);
    const requests=[...first.requests];let page=first;
    while(page.hasMore){page=await request(`/publisher/requests?cursor=${encodeURIComponent(page.cursor)}`);requests.push(...page.requests);}
    publisher={shows:shows.shows,requests};render();
  }
  function renderPublisher() {
    if(!config.publisherAccess||!user)return '';
    let body='';
    if(publisherView==='shows')body=publisher?.shows.length?`<ul>${publisher.shows.map(slug=>`<li><a href="${escape(new URL(`${slug}/`,base).href)}">${escape(slug)}</a></li>`).join('')}</ul>`:`<p>${t('noShows')}</p>`;
    if(publisherView==='requests')body=publisher?.requests.length?`<ul class="account-requests">${publisher.requests.map(row=>`<li><strong>${escape(row.showSlug||t('submit'))}</strong> — ${t(row.status)}<br><small>${escape(row.id)}</small>${row.challenge?`<p>${t('manual')}</p><code class="account-challenge">${escape(row.challenge)}</code>`:''}</li>`).join('')}</ul>`:`<p>${t('noRequests')}</p>`;
    if(['submit','claim'].includes(publisherView)) {
      const field=(key,type='text',required=true)=>`<label>${t(key)}<input name="${key}" type="${type}" maxlength="${key==='notes'?2000:320}" ${required?'required':''}></label>`;
      body=`<p>${t('manual')}</p><form data-publisher-form data-kind="${publisherView}">
        ${publisherView==='submit'?`<label>${t('source')}<select name="source"><option value="feed">RSS</option><option value="youtube">YouTube</option><option value="drive">Google Drive</option></select></label>${field('sourceUrl','url')}${field('podcastTitle','text',false)}${field('showSlug','text',false)}${field('speaker','text',false)}${field('startDate','date',false)}`:field('showSlug')+field('proofUrl','url',false)}
        ${field('contact','email',false)}<label>${t('notes')}<textarea name="notes" maxlength="2000"></textarea></label>
        <label class="account-check"><input name="rights" type="checkbox" required>${t('rights')}</label>
        <div data-publisher-turnstile></div><button class="button" type="submit">${t('send')}</button><p role="status" data-publisher-result></p></form>`;
    }
    return `<section class="panel account-publisher"><h2>${t('publisher')}</h2><nav class="account-actions" aria-label="${t('publisher')}">${['shows','submit','claim','requests'].map(key=>button(key,`publisher-${key}`,`aria-pressed="${publisherView===key}"`)).join('')}</nav><div data-publisher-content>${body}</div></section>`;
  }
  function render() {
    const menu=document.querySelector('[data-account-menu-content]');
    const toggle=document.querySelector('[data-account-toggle]');
    if(toggle) {
      const name=user?.displayName?.trim()||t('title');toggle.setAttribute('aria-label',user?`${t('title')}: ${name}`:t('title'));
      const avatar=toggle.querySelector('[data-account-avatar]');
      if(avatar) {
        if(!avatar.dataset.guestIcon)avatar.dataset.guestIcon=avatar.innerHTML;
        const words=name.trim().split(/\s+/);
        const initials=Array.from(words[0]||'')[0]+(words.length>1?Array.from(words.at(-1))[0]:'');
        const face=user?escape(initials.toLocaleUpperCase()):avatar.dataset.guestIcon;
        if(avatar.innerHTML!==face)avatar.innerHTML=face;
        const badge=document.querySelector('[data-account-menu-avatar]');
        if(badge&&badge.innerHTML!==face)badge.innerHTML=face;
      }
    }
    const name=document.querySelector('[data-account-menu-name]');
    if(name){name.textContent=user?.displayName?.trim()||t('yourAccount');name.removeAttribute('data-i18n');name.setAttribute('dir','auto');}
    const caption=document.querySelector('[data-account-menu-caption]');
    if(caption){caption.textContent=t(user?'signedIn':'syncListening');caption.removeAttribute('data-i18n');}
    if(menu) {
      let body='';
      if(oldWrapper)body+=`<p>${t('oldWrapper')}</p>`;
      else if(!user)body+=button('google','signin');
      else if(mode==='signout')body+=`<p>${t('discard')}</p>${button('stay','cancel')}${button('discardSignout','discard')}`;
      else body+=`<button type="button" class="account-menu-signout" data-account-action="signout"><svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10 5H5v14h5M9 12h12m-4-4 4 4-4 4"/></svg><span>${t('signout')}</span></button>`;
      body+=`<p role="status" aria-live="polite" data-account-problem>${problem?escape(t(problem)):''}</p>`;
      // Background sync must not replace a focused menu action.
      if(renderedMenu!==menu||renderedMenuBody!==body) {
        const focused=menu.contains(document.activeElement);
        menu.innerHTML=body;renderedMenu=menu;renderedMenuBody=body;
        if(focused)menu.querySelector('button')?.focus();
      }
    }
    const content=document.querySelector('[data-account-content]');if(!content)return;
    const form=content.querySelector('[data-publisher-form]');
    const values=form?Object.fromEntries([...form.elements].filter(e=>e.name).map(e=>[e.name,e.type==='checkbox'?e.checked:e.value])):null;
    // Preserve a filled form while background synchronization updates status.
    if(form&&user&&mode===''&&renderedLanguage===document.documentElement.lang) {
      const status=content.querySelector('[data-sync-status]');if(status)status.textContent=t(store?.status||'connecting');return;
    }
    let body=`<p>${t('explain')}</p>`;
    if(oldWrapper)body+=`<p>${t('oldWrapper')}</p>`;
    else if(!user)body+=button('google','signin');
    else {
      body+=`<p><strong>${escape(user.displayName||t('title'))}</strong></p><p role="status" aria-live="polite" data-sync-status>${t(store?.status||'connecting')}</p><div class="account-actions">${button('retry','retry')}${button('export','export')}${button('signout','signout')}${button('delete','delete')}</div>`;
      if(config.listenerAccounts&&store&&store.session.importChoice===null) {
        const records=window.TorahPodStorage.guestPreview();
        body+=`<section class="panel account-import"><h2>${t('import')}</h2><p>${t('preview')}</p><p>${['follows','saved','progress'].map((kind,i)=>`${t(['followCount','savedCount','progressCount'][i])}: ${records.filter(r=>r.kind===kind).length}`).join(' · ')}</p><div class="account-actions">${button('import','import')}${button('separate','separate')}</div></section>`;
      }
      for(const [key,conflict] of Object.entries(store?.session.conflicts||{})) {
        const pos=conflict.local.kind==='progress';
        body+=`<section class="panel account-conflict"><p>${t('conflict')}</p><p>${escape(store.session.metadata[key]?.title||conflict.local.id)}</p>${pos?`<p>${Math.round(conflict.local.value.position)}s / ${Math.round(conflict.cloud?.value?.position||0)}s</p>`:''}<div class="account-actions">${button(pos?'devicePosition':'deviceChange','device',`data-conflict-key="${escape(key)}"`)}${button(pos?'cloudPosition':'cloudChange','cloud',`data-conflict-key="${escape(key)}"`)}</div></section>`;
      }
      if(mode==='signout')body+=`<section class="panel"><p>${t('discard')}</p><div class="account-actions">${button('stay','cancel')}${button('discardSignout','discard')}</div></section>`;
      if(mode==='delete')body+=`<section class="panel"><p>${t('deletion')}</p><div class="account-actions">${button('cancel','cancel')}${button('confirmDelete','confirm-delete')}</div></section>`;
      body+=renderPublisher();
    }
    destroyPublisherWidget();renderedLanguage=document.documentElement.lang;
    content.innerHTML=body+`<p role="status" aria-live="polite" data-account-problem>${problem?escape(t(problem)):''}</p>`;
    if(values)for(const element of content.querySelectorAll('[data-publisher-form] [name]'))if(element.name in values){if(element.type==='checkbox')element.checked=values[element.name];else element.value=values[element.name];}
    if(content.querySelector('[data-publisher-form]'))setupPublisherForm(content.querySelector('[data-publisher-form]'));
  }
  async function setupPublisherForm(form) {
    let token='',widget=null;
    try {
      if(!window.turnstile)await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';script.onload=resolve;script.onerror=reject;document.head.append(script);});
      if(!form.isConnected)return;
      widget=window.turnstile.render(form.querySelector('[data-publisher-turnstile]'),{sitekey:document.querySelector('[data-account-page]').dataset.turnstileSiteKey,action:'onboarding',callback:value=>{token=value;},'expired-callback':()=>{token='';}});
      destroyPublisherWidget=()=>{if(widget!==null)window.turnstile.remove(widget);};
    }catch{}
    form.addEventListener('submit',async event=>{
      event.preventDefault();const submit=form.querySelector('button[type="submit"]'),result=form.querySelector('[data-publisher-result]');submit.disabled=true;
      try {
        if(!token)throw new Error('verification_required');
        const data=Object.fromEntries(new FormData(form));
        const payload=form.dataset.kind==='claim'?{contact:data.contact,notes:data.notes,proofUrl:data.proofUrl,authorizationConfirmed:data.rights==='on',turnstileToken:token}
          :{source:data.source,sourceUrl:data.sourceUrl,title:data.podcastTitle,slug:data.showSlug,speaker:data.speaker,startDate:data.startDate,contact:data.contact,notes:data.notes,authorizationConfirmed:data.rights==='on',turnstileToken:token};
        // Turnstile tokens expire between retries; stable request content excludes
        // that transient token from its idempotency digest on the server.
        if(!publisherAttempt||publisherAttempt.kind!==form.dataset.kind)publisherAttempt={kind:form.dataset.kind,frozen:{operationId:crypto.randomUUID(),showSlug:form.dataset.kind==='claim'?data.showSlug:undefined,payload}};
        const frozen=publisherAttempt.frozen;
        frozen.payload.turnstileToken=token;
        await request(`/publisher/${form.dataset.kind==='claim'?'claims':'requests'}`,{method:'POST',body:frozen});
        publisherAttempt=null;publisherView='requests';mode='';contentReset();await loadPublisher();
      }catch(error){if(error.body?.error==='request_not_accepted')publisherAttempt=null;result.textContent=t(error.body?.error==='request_pending'?'requestPending':'failure');}
      finally{submit.disabled=false;token='';if(widget!==null)window.turnstile.reset(widget);}
    });
  }
  function contentReset(){document.querySelector('[data-account-content]')?.replaceChildren();}
  document.addEventListener('click',event=>{
    const control=event.target.closest?.('[data-account-action]');if(!control)return;
    const action=control.dataset.accountAction;
    if(action==='signin') {
      // The SDK is already loaded before showing sign-in: popup launch is synchronous with
      // this user gesture, with no intervening await or page navigation.
      auth.signIn().catch(()=>{problem='authFailure';render();});return;
    }
    if(action.startsWith('publisher-')){publisherView=action.slice(10);contentReset();render();if(['shows','requests'].includes(publisherView))void loadPublisher().catch(()=>{problem=t('failure');render();});return;}
    control.disabled=true;
    void (async()=>{
      problem='';
      if(action==='retry') {if(store?.status==='reauthentication')await auth.reauthenticate();await store?.flush(true);}
      if(action==='export') {const data=await request('/export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='torah-pod-account.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
      if(action==='signout')await signout();
      if(action==='discard')await signout(true);
      if(action==='cancel')mode='';
      if(action==='delete')mode='delete';
      if(action==='confirm-delete') {
        try{await request('/me',{method:'DELETE'});}catch(error){if(error.body?.error!=='recent_authentication_required')throw error;await auth.reauthenticate();await request('/me',{method:'DELETE'});}
        await removeDeleted();
      }
      if(action==='import')await store.importGuest(window.TorahPodStorage.guestPreview());
      if(action==='separate')await store.update(s=>{s.importChoice='separate';return s;});
      if(['cloud','device'].includes(action))await store.resolve(control.dataset.conflictKey,action==='device');
      render();
    })().catch(error=>{if(error.body?.error==='account_deleted'){void removeDeleted();return;}problem='failure';render();}).finally(()=>{if(control.isConnected)control.disabled=false;});
  });
  document.addEventListener('torahpod:storageerror',()=>{problem='failure';render();});
  window.addEventListener('online',()=>{store?.schedule(0);});
  window.addEventListener('pagehide',()=>{void store?.flush(true);});
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')void store?.flush(true);else store?.schedule(0);});
  if(auth)auth.subscribe(next=>{switching=switching.then(()=>changed(next)).catch(()=>{problem='failure';render();});});
  render();return {render};
}
