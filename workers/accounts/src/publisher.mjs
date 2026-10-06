import { APIError, boundedString, integer, exactKeys, invalid, fingerprint } from './errors.mjs';
import { validateItem } from './library.mjs';

const statuses=['submitted','under_review','needs_information','approved','published','declined'];
export const publicRequest = row => ({ id:row.request_id,kind:row.kind,showSlug:row.show_slug,
  status:row.status,revision:row.revision,challenge:row.challenge,createdAt:row.created_at });

export async function listRequests(db,uid,params,claimsOnly=false) {
  const after=params.get('cursor')||''; if (after) boundedString(after,128);
  const { results }=await db.prepare(`SELECT * FROM publisher_requests WHERE uid=? AND request_id>? ${claimsOnly ? "AND kind='claim'" : ''} ORDER BY request_id LIMIT 51`).bind(uid,after).all();
  return { requests:results.slice(0,50).map(publicRequest),hasMore:results.length>50,cursor:results[49]?.request_id||after };
}
export async function createRequest(env,user,kind,raw) {
  exactKeys(raw,['operationId','showSlug','payload']); boundedString(raw.operationId,128);
  if (!raw.payload || typeof raw.payload!=='object' || Array.isArray(raw.payload)) invalid();
  // All contact/evidence fields are sent privately to intake, never persisted
  // in D1. A digest detects reuse of an operation ID with changed contents.
  const showSlug=kind==='claim' ? boundedString(raw.showSlug,80) : '';
  if (showSlug) validateItem('follows',showSlug);
  if (!env.ONBOARDING || !env.PUBLISHER_SERVICE_TOKEN) throw new APIError(503,'service_unavailable');
  const {turnstileToken:_verification,...stablePayload}=raw.payload;
  const hash=await fingerprint({kind,showSlug,payload:stablePayload});
  const id=crypto.randomUUID(),challenge=kind==='claim' ? `torahpod-claim-${crypto.randomUUID()}` : '';
  await env.DB.prepare(`INSERT INTO publisher_requests(request_id,uid,operation_id,fingerprint,kind,show_slug,challenge,created_at)
    VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(uid,operation_id) DO NOTHING`).bind(id,user.uid,raw.operationId,hash,kind,showSlug,challenge,Date.now()).run();
  let row=await env.DB.prepare('SELECT * FROM publisher_requests WHERE uid=? AND operation_id=?').bind(user.uid,raw.operationId).first();
  if (row.fingerprint!==hash) throw new APIError(409,'operation_reused');
  if (row.delivery==='delivered') return publicRequest(row);
  const now=Date.now();
  const lease=await env.DB.prepare(`UPDATE publisher_requests SET lease_until=?,delivery='uncertain'
    WHERE uid=? AND request_id=? AND lease_until<? AND delivery!='delivered'
    AND EXISTS(SELECT 1 FROM accounts WHERE uid=? AND state='active') RETURNING request_id`)
    .bind(now+60000,user.uid,row.request_id,now,user.uid).first();
  if (!lease) return publicRequest(row);
  let response;
  try {
    response=await env.ONBOARDING.fetch('https://onboarding.internal/internal/publisher',{
      method:'POST',headers:{ 'Content-Type':'application/json','X-Publisher-Service-Token':env.PUBLISHER_SERVICE_TOKEN },
      body:JSON.stringify({ requestId:row.request_id,uid:user.uid,environment:env.ENVIRONMENT,
        kind,showSlug,challenge:row.challenge,allowCreate:row.delivery==='reserved',payload:raw.payload }),
      signal:AbortSignal.timeout(20000),
    });
    const result=await response.json();
    if (response.ok && result.delivered===true) {
      await env.DB.prepare("UPDATE publisher_requests SET delivery='delivered',lease_until=0 WHERE uid=? AND request_id=?").bind(user.uid,row.request_id).run();
    } else if ([400,403,409].includes(response.status) && result.safeToRetry===true) {
      await env.DB.prepare("UPDATE publisher_requests SET delivery='reserved',lease_until=0 WHERE uid=? AND request_id=?").bind(user.uid,row.request_id).run();
      throw new APIError(response.status,'request_not_accepted');
    } else {
      await env.DB.prepare('UPDATE publisher_requests SET lease_until=0 WHERE uid=? AND request_id=?').bind(user.uid,row.request_id).run();
      throw new APIError(503,'request_pending');
    }
  } catch(error) {
    // An ambiguous POST is reconciliation-only on all subsequent retries. Do
    // not create a second private issue merely because search is delayed.
    if (error instanceof APIError) throw error;
    throw new APIError(503,'request_pending');
  }
  return publicRequest(row);
}

export async function statusEvent(env,raw) {
  exactKeys(raw,['eventId','requestId','revision','status','showSlug','verifiedOwnership','publicationVerified']);
  boundedString(raw.eventId,128); boundedString(raw.requestId,128); integer(raw.revision);
  if (raw.revision<1 || !statuses.includes(raw.status)) invalid();
  const slug=raw.showSlug||''; if (slug) validateItem('follows',slug);
  if (raw.verifiedOwnership!==undefined && typeof raw.verifiedOwnership!=='boolean') invalid();
  if (raw.publicationVerified!==undefined && typeof raw.publicationVerified!=='boolean') invalid();
  const hash=await fingerprint(raw);
  const prior=await env.DB.prepare('SELECT fingerprint FROM publisher_events WHERE event_id=?').bind(raw.eventId).first();
  if (prior) {
    if (prior.fingerprint!==hash) throw new APIError(409,'operation_reused');
    return { accepted:true };
  }
  const row=await env.DB.prepare(`SELECT r.* FROM publisher_requests r JOIN accounts a ON a.uid=r.uid
    WHERE r.request_id=? AND a.state='active'`).bind(raw.requestId).first();
  if (!row) throw new APIError(404,'not_found');
  if (raw.revision<=row.revision) return { accepted:true };
  if (row.kind==='claim' && raw.status==='published') invalid();
  if (['published','declined'].includes(row.status) && raw.status!==row.status) throw new APIError(409,'status_conflict');
  if (row.status==='approved' && !['approved','published'].includes(raw.status)) throw new APIError(409,'status_conflict');
  if (row.revision>0 && raw.status==='submitted' && row.status!=='submitted') throw new APIError(409,'status_conflict');
  if (row.kind==='claim' && raw.status==='approved' && (raw.verifiedOwnership!==true || !slug || slug!==row.show_slug)) invalid();
  if (raw.status==='published' && (raw.publicationVerified!==true || !slug)) invalid();
  const statements=[
    env.DB.prepare('INSERT INTO publisher_events(event_id,request_id,fingerprint,expected_revision) VALUES(?,?,?,?)').bind(raw.eventId,raw.requestId,hash,row.revision),
    env.DB.prepare(`UPDATE publisher_requests SET status=?,revision=?,show_slug=CASE WHEN ?!='' THEN ? ELSE show_slug END
      WHERE request_id=? AND uid=? AND revision=? AND EXISTS(SELECT 1 FROM accounts WHERE uid=? AND state='active')`)
      .bind(raw.status,raw.revision,slug,slug,raw.requestId,row.uid,row.revision,row.uid),
  ];
  if (raw.verifiedOwnership===true && slug && ['approved','published'].includes(raw.status)) {
    statements.push(env.DB.prepare(`INSERT INTO publisher_shows(uid,show_slug,request_id)
      SELECT uid,show_slug,request_id FROM publisher_requests WHERE request_id=? AND uid=? AND revision=?
        AND status IN ('approved','published') AND EXISTS(SELECT 1 FROM accounts WHERE uid=? AND state='active')
      ON CONFLICT(uid,show_slug) DO NOTHING`).bind(raw.requestId,row.uid,raw.revision,row.uid));
  }
  try { await env.DB.batch(statements); }
  catch(error) {
    const retry=await env.DB.prepare('SELECT fingerprint FROM publisher_events WHERE event_id=?').bind(raw.eventId).first();
    if (retry?.fingerprint===hash) return { accepted:true };
    if (String(error.message).includes('status_conflict')) throw new APIError(409,'status_conflict');
    throw error;
  }
  const updated=await env.DB.prepare('SELECT revision FROM publisher_requests WHERE request_id=? AND uid=?').bind(raw.requestId,row.uid).first();
  if (updated?.revision!==raw.revision && (updated?.revision||0)<raw.revision) throw new APIError(409,'status_conflict');
  return { accepted:true };
}
