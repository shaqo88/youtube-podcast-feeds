import { createRemoteJWKSet, jwtVerify, SignJWT, importPKCS8 } from 'jose';
import { APIError } from './errors.mjs';

const googleKeys = createRemoteJWKSet(new URL('https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com'));
const accessTokens = new Map();
const checkedAccounts = new Map();
const unauthorized = () => { throw new APIError(401,'authentication_required'); };

export async function googleAccessToken(env, fetcher = fetch) {
  const project = env.FIREBASE_PROJECT_ID;
  const cached = accessTokens.get(project);
  if (cached && cached.expires > Date.now()) return cached.token;
  let credential;
  try { credential = JSON.parse(env.GOOGLE_ACCOUNT_SERVICE_JSON); } catch { throw new APIError(503,'service_unavailable'); }
  if (credential.project_id !== project || !credential.client_email || !credential.private_key) throw new APIError(503,'service_unavailable');
  const key = await importPKCS8(credential.private_key,'RS256');
  const assertion = await new SignJWT({ scope: 'https://www.googleapis.com/auth/identitytoolkit' })
    .setProtectedHeader({ alg:'RS256', typ:'JWT' }).setIssuer(credential.client_email)
    .setAudience('https://oauth2.googleapis.com/token').setIssuedAt().setExpirationTime('1h').sign(key);
  const response = await fetcher('https://oauth2.googleapis.com/token', {
    method:'POST', headers:{ 'Content-Type':'application/x-www-form-urlencoded' },
    body:new URLSearchParams({ grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer', assertion }),
    signal:AbortSignal.timeout(10000),
  });
  const body = await response.json();
  if (!response.ok || typeof body.access_token !== 'string') throw new APIError(503,'service_unavailable');
  if (accessTokens.size > 4) accessTokens.clear();
  accessTokens.set(project,{ token:body.access_token, expires:Date.now() + Math.min(Number(body.expires_in)||3600,3600)*1000-60000 });
  return body.access_token;
}

export async function googleAccountCall(env, method, body, fetcher = fetch) {
  const token = await googleAccessToken(env,fetcher);
  const response = await fetcher(`https://identitytoolkit.googleapis.com/v1/projects/${encodeURIComponent(env.FIREBASE_PROJECT_ID)}/accounts:${method}`, {
    method:'POST', headers:{ Authorization:`Bearer ${token}`, 'Content-Type':'application/json' },
    body:JSON.stringify(body), signal:AbortSignal.timeout(10000),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (method === 'delete' && result.error?.message === 'USER_NOT_FOUND') return {};
    throw new APIError(503,'service_unavailable');
  }
  return result;
}

export async function checkAccount(env, claims, fresh = false, call = googleAccountCall) {
  const key = `${env.FIREBASE_PROJECT_ID}:${claims.sub}`;
  let entry = checkedAccounts.get(key);
  if (fresh || !entry || entry.expires <= Date.now()) {
    const result = await call(env,'lookup',{ localId:[claims.sub] });
    const user = result.users?.find(u => u.localId === claims.sub);
    if (!user || user.disabled === true) {
      checkedAccounts.delete(key); throw new APIError(401,!user?'account_deleted':'account_unavailable');
    }
    entry = { user, expires:Date.now()+60000 };
    if (checkedAccounts.size >= 1000) checkedAccounts.clear();
    checkedAccounts.set(key,entry);
  }
  if (claims.auth_time < Number(entry.user.validSince || 0)) unauthorized();
  return entry.user;
}

export function forgetAccount(env, uid) { checkedAccounts.delete(`${env.FIREBASE_PROJECT_ID}:${uid}`); }

export async function authenticate(request, env, { fresh = false, keys = googleKeys, call = googleAccountCall } = {}) {
  const header = request.headers.get('Authorization') || '';
  if (!/^Bearer [A-Za-z0-9._-]{1,8192}$/.test(header) || !env.FIREBASE_PROJECT_ID) unauthorized();
  let claims;
  try {
    const verified = await jwtVerify(header.slice(7), keys, {
      algorithms:['RS256'], issuer:`https://securetoken.google.com/${env.FIREBASE_PROJECT_ID}`,
      audience:env.FIREBASE_PROJECT_ID, requiredClaims:['exp','iat','sub','auth_time'],
    });
    claims = verified.payload;
    const now = Math.floor(Date.now()/1000);
    if (typeof claims.sub !== 'string' || !claims.sub.length || claims.sub.length > 128 || /[\u0000-\u001f]/.test(claims.sub)
      || !Number.isInteger(claims.iat) || claims.iat > now || !Number.isInteger(claims.auth_time)
      || claims.auth_time > now || claims.auth_time > claims.iat || claims.firebase?.sign_in_provider !== 'google.com') unauthorized();
  } catch { unauthorized(); }
  const user = await checkAccount(env,claims,fresh,call);
  return { uid:claims.sub, authTime:claims.auth_time, displayName:String(user.displayName || '').slice(0,200) };
}
