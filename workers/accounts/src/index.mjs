import { authenticate } from './auth.mjs';
import { APIError, readJSON, fingerprint } from './errors.mjs';
import { mutate,libraryPage,importGuest,record } from './library.mjs';
import { requestDeletion,runDeletionJobs } from './deletion.mjs';
import { createRequest,listRequests,statusEvent,publicRequest } from './publisher.mjs';

export const enabled=value=>value==='true';
function response(request,env,status,body,extra={}) {
  const origin=request.headers.get('Origin');
  const allowed=String(env.ALLOWED_ORIGINS||'').split(',').includes(origin);
  return new Response(body===null ? null : JSON.stringify(body),{ status,headers:{
    'Content-Type':'application/json; charset=utf-8','Cache-Control':'private, no-store',
    'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Vary':'Origin',
    ...(allowed ? { 'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Methods':'GET,PUT,POST,DELETE,OPTIONS',
      'Access-Control-Allow-Headers':'Authorization,Content-Type','Access-Control-Expose-Headers':'Retry-After' } : {}),...extra,
  } });
}
async function limit(binding,key) {
  if (!binding || !(await binding.limit({key})).success) throw new APIError(429,'try_later');
}
async function internalAuthorized(request,env) {
  if (!env.INTERNAL_STATUS_TOKEN) return false;
  const actual=await fingerprint(request.headers.get('Authorization')||'');
  const expected=await fingerprint(`Bearer ${env.INTERNAL_STATUS_TOKEN}`);
  return actual===expected;
}
export function createHandler(auth=authenticate,deletionRunner=runDeletionJobs) {
  return async (request,env,ctx={waitUntil(){}})=>{
    try {
      const url=new URL(request.url),path=url.pathname;
      if (path==='/health' && request.method==='GET') return response(request,env,200,{ok:true,revision:env.BUILD_SHA||''});
      if (path==='/api/v1/internal/health') {
        if(request.method!=='GET'||!(await internalAuthorized(request,env)))throw new APIError(404,'not_found');
        await limit(env.INTERNAL_LIMITER,'health');
        const queue=await env.DB.prepare('SELECT count(*) AS pending,coalesce(max(attempts),0) AS maximumAttempts,coalesce(min(next_attempt),0) AS nextAttempt FROM deletion_jobs').first();
        const delivery=await env.DB.prepare("SELECT count(*) AS pending FROM publisher_requests WHERE delivery!='delivered'").first();
        return response(request,env,200,{ok:true,revision:env.BUILD_SHA||'',deletion:queue,publisher:delivery});
      }
      if (path==='/api/v1/internal/publisher/status') {
        if (!enabled(env.PUBLISHER_ACCESS) || request.method!=='POST' || !(await internalAuthorized(request,env))) throw new APIError(404,'not_found');
        await limit(env.INTERNAL_LIMITER,'publisher-status');
        return response(request,env,200,await statusEvent(env,await readJSON(request)));
      }
      if (!path.startsWith('/api/v1/')) throw new APIError(404,'not_found');
      const origin=request.headers.get('Origin');
      if (origin && !String(env.ALLOWED_ORIGINS||'').split(',').includes(origin)) throw new APIError(403,'origin_denied');
      if (request.method==='OPTIONS') {
        if (!origin) throw new APIError(403,'origin_denied');
        return response(request,env,204,null);
      }
      const publisher=path.startsWith('/api/v1/publisher/');
      const foundation=['/api/v1/me','/api/v1/export'].includes(path);
      if (foundation ? !enabled(env.LISTENER_ACCOUNTS)&&!enabled(env.PUBLISHER_ACCESS)
        : publisher ? !enabled(env.PUBLISHER_ACCESS) : !enabled(env.LISTENER_ACCOUNTS)) throw new APIError(404,'feature_unavailable');
      await limit(env.IP_LIMITER,request.headers.get('CF-Connecting-IP')||'unknown');
      const deleting=path==='/api/v1/me' && request.method==='DELETE';
      const user=await auth(request,env,{fresh:deleting});
      await limit(env.USER_LIMITER,user.uid);
      const uidHash=await fingerprint([env.FIREBASE_PROJECT_ID,user.uid]);
      if (await env.DB.prepare('SELECT 1 FROM deleted_accounts WHERE uid_hash=?').bind(uidHash).first()) throw new APIError(401,'account_deleted');
      await env.DB.prepare(`INSERT INTO accounts(uid,uid_hash,display_name,created_at) VALUES(?,?,?,?)
        ON CONFLICT(uid) DO UPDATE SET display_name=CASE WHEN state='active' THEN excluded.display_name ELSE display_name END`)
        .bind(user.uid,uidHash,user.displayName,Date.now()).run();
      const account=await env.DB.prepare('SELECT uid,display_name,state,created_at FROM accounts WHERE uid=?').bind(user.uid).first();
      if (account.state!=='active') {
        if (deleting) return response(request,env,202,{accepted:true});
        throw new APIError(401,'account_deleted');
      }
      if (path==='/api/v1/me' && request.method==='GET') return response(request,env,200,{ uid:user.uid,displayName:account.display_name,
        capabilities:{listenerAccounts:enabled(env.LISTENER_ACCOUNTS),publisherAccess:enabled(env.PUBLISHER_ACCESS)} });
      if (deleting) {
        const result=await requestDeletion(env,user);
        ctx.waitUntil(deletionRunner(env));
        return response(request,env,202,result);
      }
      if (path==='/api/v1/library' && request.method==='GET') return response(request,env,200,await libraryPage(env.DB,user.uid,url.searchParams));
      if (path==='/api/v1/import' && request.method==='POST') return response(request,env,200,await importGuest(env.DB,user.uid,await readJSON(request,65536)));
      const item=path.match(/^\/api\/v1\/(follows|saved|progress)\/([^/]+)$/);
      if (item && (request.method==='PUT' || (request.method==='DELETE' && item[1]!=='progress'))) {
        let id; try { id=decodeURIComponent(item[2]); } catch { throw new APIError(400,'invalid_request'); }
        return response(request,env,200,await mutate(env.DB,user.uid,item[1],id,await readJSON(request),request.method==='DELETE'));
      }
      if (path==='/api/v1/export' && request.method==='GET') {
        const [library,requests,shows]=await env.DB.batch([
          env.DB.prepare('SELECT * FROM library WHERE uid=? ORDER BY kind,item_id').bind(user.uid),
          env.DB.prepare('SELECT * FROM publisher_requests WHERE uid=? ORDER BY request_id').bind(user.uid),
          env.DB.prepare('SELECT show_slug FROM publisher_shows WHERE uid=? ORDER BY show_slug').bind(user.uid),
        ]);
        return response(request,env,200,{ schemaVersion:1,profile:{uid:user.uid,displayName:account.display_name,createdAt:account.created_at},
          library:library.results.map(record),publisherRequests:requests.results.map(publicRequest),publisherShows:shows.results.map(s=>s.show_slug) },
          {'Content-Disposition':'attachment; filename="torah-pod-account.json"'});
      }
      if (publisher) {
        if (path==='/api/v1/publisher/shows' && request.method==='GET') {
          const {results}=await env.DB.prepare('SELECT show_slug FROM publisher_shows WHERE uid=? ORDER BY show_slug').bind(user.uid).all();
          return response(request,env,200,{shows:results.map(s=>s.show_slug)});
        }
        if (path==='/api/v1/publisher/requests' && request.method==='GET') return response(request,env,200,await listRequests(env.DB,user.uid,url.searchParams));
        if (path==='/api/v1/publisher/claims' && request.method==='GET') return response(request,env,200,await listRequests(env.DB,user.uid,url.searchParams,true));
        const detail=path.match(/^\/api\/v1\/publisher\/(requests|claims)\/([a-zA-Z0-9-]+)$/);
        if (detail && request.method==='GET') {
          const row=await env.DB.prepare('SELECT * FROM publisher_requests WHERE uid=? AND request_id=?').bind(user.uid,detail[2]).first();
          if (!row || (detail[1]==='claims' && row.kind!=='claim')) throw new APIError(404,'not_found');
          return response(request,env,200,publicRequest(row));
        }
        if (['/api/v1/publisher/requests','/api/v1/publisher/claims'].includes(path) && request.method==='POST') {
          await limit(env.PUBLISHER_LIMITER,user.uid);
          return response(request,env,201,await createRequest(env,user,path.endsWith('/claims')?'claim':'submission',await readJSON(request)));
        }
      }
      throw new APIError(404,'not_found');
    } catch(error) {
      if (error instanceof APIError) return response(request,env,error.status,{error:error.code,...error.extra},error.status===429?{'Retry-After':'60'}:{});
      if (String(error.message).includes('account_blocked')) return response(request,env,401,{error:'account_deleted'});
      console.warn('account_api_unavailable');
      return response(request,env,503,{error:'service_unavailable'});
    }
  };
}
export default { fetch:createHandler(),scheduled:(_event,env,ctx)=>ctx.waitUntil(runDeletionJobs(env)) };
