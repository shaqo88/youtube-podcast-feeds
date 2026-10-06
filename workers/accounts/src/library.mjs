import { APIError, boundedString, integer, exactKeys, invalid, fingerprint } from './errors.mjs';

export const record = row => row ? ({ kind:row.kind,id:row.item_id,value:JSON.parse(row.value),
  deleted:Boolean(row.deleted),revision:row.revision,updatedAt:row.updated_at }) : null;
export async function current(db, uid, kind, id) {
  return record(await db.prepare('SELECT * FROM library WHERE uid=? AND kind=? AND item_id=?').bind(uid,kind,id).first());
}
export function validateItem(kind,id) {
  boundedString(id,512);
  if (kind === 'follows') { if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id) || id.length>80) invalid(); }
  else if (!/^[a-z0-9-]+:.+/.test(id)) invalid();
}
export function validateValue(kind, raw) {
  if (kind !== 'progress') { exactKeys(raw,[]); return {}; }
  exactKeys(raw,['position','duration','completed','recordedAt']);
  if (typeof raw.position !== 'number' || !Number.isFinite(raw.position) || raw.position<0 || raw.position>86400
    || typeof raw.duration !== 'number' || !Number.isFinite(raw.duration) || raw.duration<0 || raw.duration>86400
    || (raw.duration>0 && raw.position>raw.duration+1) || typeof raw.completed !== 'boolean') invalid();
  // Null means the guest record had no timestamp. Never give legacy records a
  // synthetic timestamp which might replace a newer cloud listening position.
  if (raw.recordedAt !== null) integer(raw.recordedAt,Date.now()+300000);
  return { position:raw.position,duration:raw.duration,completed:raw.completed,recordedAt:raw.recordedAt };
}
export function operationStatement(db,uid,op,hash) {
  return db.prepare(`INSERT INTO operations(uid,operation_id,fingerprint,kind,item_id,expected_revision,value,deleted,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(uid,operation_id) DO NOTHING`).bind(uid,op.operationId,hash,
    op.kind,op.id,op.expectedRevision,JSON.stringify(op.value),Number(op.deleted),Date.now());
}
export async function mutate(db,uid,kind,id,raw,deleted) {
  exactKeys(raw,['operationId','expectedRevision','value']); validateItem(kind,id);
  const op = { operationId:boundedString(raw.operationId,128), expectedRevision:integer(raw.expectedRevision),
    kind,id,value:deleted ? {} : validateValue(kind,raw.value),deleted };
  const hash = await fingerprint(op);
  try { await operationStatement(db,uid,op,hash).run(); }
  catch (error) {
    if (String(error.message).includes('revision_conflict')) throw new APIError(409,'revision_conflict',{ current:await current(db,uid,kind,id) });
    if (String(error.message).includes('account_blocked')) throw new APIError(401,'account_deleted');
    throw error;
  }
  const receipt = await db.prepare('SELECT fingerprint,result FROM operations WHERE uid=? AND operation_id=?').bind(uid,op.operationId).first();
  if (receipt.fingerprint !== hash) throw new APIError(409,'operation_reused');
  const result=JSON.parse(receipt.result);result.deleted=Boolean(result.deleted);return result;
}
export async function libraryPage(db,uid,params) {
  const parse = (key, fallback) => params.has(key) ? integer(Number(params.get(key))) : fallback;
  const after = parse('cursor',0);
  const maximum = await db.prepare('SELECT COALESCE(MAX(sequence),0) AS cursor FROM changes WHERE uid=?').bind(uid).first();
  const until = parse('until',maximum.cursor);
  const limit = parse('limit',100);
  if (!limit || limit>200 || until>maximum.cursor || after>until) invalid();
  const { results } = await db.prepare('SELECT * FROM changes WHERE uid=? AND sequence>? AND sequence<=? ORDER BY sequence LIMIT ?')
    .bind(uid,after,until,limit+1).all();
  const more = results.length>limit, rows=results.slice(0,limit);
  return { records:rows.map(record),cursor:more ? rows.at(-1).sequence : until,until,hasMore:more };
}
export async function importGuest(db,uid,raw) {
  exactKeys(raw,['importId','records']); boundedString(raw.importId,128);
  if (!Array.isArray(raw.records) || raw.records.length>50) invalid();
  const hash = await fingerprint(raw);
  const prior = await db.prepare('SELECT fingerprint,result FROM imports WHERE uid=? AND import_id=?').bind(uid,raw.importId).first();
  if (prior) {
    if (prior.fingerprint !== hash) throw new APIError(409,'operation_reused');
    return JSON.parse(prior.result);
  }
  const statements=[]; const seen=new Set(); let applied=0;
  for (const [index,item] of raw.records.entries()) {
    exactKeys(item,['kind','id','value']);
    if (!['follows','saved','progress'].includes(item.kind)) invalid();
    validateItem(item.kind,item.id); const value=validateValue(item.kind,item.value);
    const key=`${item.kind}:${item.id}`; if (seen.has(key)) invalid(); seen.add(key);
    const cloud=await current(db,uid,item.kind,item.id);
    // Respect removal markers; imports never revive a cloud removal. Unknown
    // legacy update times and equal timestamps always keep existing cloud data.
    if (cloud && (item.kind!=='progress' || cloud.deleted || value.recordedAt===null
      || value.recordedAt <= (cloud.value.recordedAt ?? cloud.updatedAt))) continue;
    const op={ operationId:`import:${raw.importId}:${index}`,expectedRevision:cloud?.revision||0,
      kind:item.kind,id:item.id,value,deleted:false };
    statements.push(operationStatement(db,uid,op,await fingerprint(op))); applied++;
  }
  const result={ applied,skipped:raw.records.length-applied };
  statements.push(db.prepare('INSERT INTO imports(uid,import_id,fingerprint,result) VALUES(?,?,?,?)')
    .bind(uid,raw.importId,hash,JSON.stringify(result)));
  try { await db.batch(statements); }
  catch(error) {
    const retry=await db.prepare('SELECT fingerprint,result FROM imports WHERE uid=? AND import_id=?').bind(uid,raw.importId).first();
    if (retry?.fingerprint===hash) return JSON.parse(retry.result);
    if (String(error.message).includes('revision_conflict')) throw new APIError(409,'import_conflict');
    throw error;
  }
  return result;
}
