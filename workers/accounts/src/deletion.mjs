import { googleAccountCall, forgetAccount } from './auth.mjs';
import { APIError } from './errors.mjs';

export async function requestDeletion(env,user) {
  if (Math.floor(Date.now()/1000)-user.authTime>300) throw new APIError(403,'recent_authentication_required');
  await env.DB.batch([
    env.DB.prepare('INSERT INTO deleted_accounts(uid_hash) SELECT uid_hash FROM accounts WHERE uid=? ON CONFLICT(uid_hash) DO NOTHING').bind(user.uid),
    env.DB.prepare("UPDATE accounts SET state='deleting' WHERE uid=?").bind(user.uid),
    env.DB.prepare('INSERT INTO deletion_jobs(uid,next_attempt) VALUES(?,?) ON CONFLICT(uid) DO NOTHING').bind(user.uid,Date.now()),
  ]);
  forgetAccount(env,user.uid);
  return { accepted:true };
}
export async function runDeletionJobs(env,call=googleAccountCall) {
  const now=Date.now();
  const { results }=await env.DB.prepare('SELECT uid,attempts FROM deletion_jobs WHERE next_attempt<=? AND lease_until<? LIMIT 20').bind(now,now).all();
  let failed=0,completed=0;
  for (const job of results) {
    const lease=await env.DB.prepare('UPDATE deletion_jobs SET lease_until=? WHERE uid=? AND lease_until<? RETURNING uid').bind(now+60000,job.uid,now).first();
    if (!lease) continue;
    try {
      // Remove D1 payloads before dependency calls. The account barrier and job
      // survive until Google identity deletion succeeds; retries are safe.
      await env.DB.batch(['library','changes','operations','imports','publisher_shows','publisher_requests']
        .map(table=>env.DB.prepare(`DELETE FROM ${table} WHERE uid=?`).bind(job.uid)));
      await call(env,'delete',{ localId:job.uid });
      await env.DB.prepare('DELETE FROM accounts WHERE uid=? AND state=?').bind(job.uid,'deleting').run();
      forgetAccount(env,job.uid); completed++;
    } catch {
      failed++;
      await env.DB.prepare('UPDATE deletion_jobs SET attempts=attempts+1,next_attempt=?,lease_until=0 WHERE uid=?')
        .bind(now+Math.min(86400000,30000*2**Math.min(job.attempts,12)),job.uid).run();
    }
  }
  if (failed) console.warn('account_deletion_retry',{ count:failed });
  return { completed,failed };
}
