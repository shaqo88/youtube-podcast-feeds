import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
const environment=process.argv[2];
if(!['preview','production'].includes(environment))throw new Error('Choose preview or production');
const config=JSON.parse(readFileSync(`config/accounts.${environment}.json`));
const other=JSON.parse(readFileSync(`config/accounts.${environment==='production'?'preview':'production'}.json`));
if(config.environment!==environment||typeof config.listenerAccounts!=='boolean'||typeof config.publisherAccess!=='boolean')throw new Error('Invalid environment flags');
if(config.firebase?.projectId&&config.firebase.projectId===other.firebase?.projectId)throw new Error('Identity projects must be isolated');
const id=process.env.ACCOUNTS_D1_ID;
if(!/^[0-9a-f-]{36}$/.test(id||''))throw new Error('Configure a separate account D1 database');
if(id===process.env.OTHER_ACCOUNTS_D1_ID)throw new Error('Account databases must be isolated');
const base=JSON.parse(readFileSync('workers/accounts/wrangler.json'));
base.name=`torah-pod-accounts-${environment}`;
base.main=resolve('workers/accounts/src/index.mjs');
base.vars={ENVIRONMENT:environment,FIREBASE_PROJECT_ID:config.firebase?.projectId||`torah-pod-accounts-${environment==='production'?'prod':'preview'}`,
  LISTENER_ACCOUNTS:String(config.listenerAccounts),PUBLISHER_ACCESS:String(config.publisherAccess),
  ALLOWED_ORIGINS:environment==='production'?'https://torah-pod.pages.dev,https://shaqo88.github.io':'https://accounts-preview.torah-pod.pages.dev'};
base.d1_databases=[{binding:'DB',database_name:`torah-pod-accounts-${environment}`,database_id:id,migrations_dir:resolve('workers/accounts/migrations')}];
base.services=[{binding:'ONBOARDING',service:environment==='production'?'youtube-podcast-onboarding':'youtube-podcast-onboarding-preview'}];
if(environment==='preview')for(const limiter of base.ratelimits)limiter.namespace_id=String(Number(limiter.namespace_id)+100);
mkdirSync('tmp',{recursive:true});writeFileSync(`tmp/accounts-${environment}.json`,JSON.stringify(base,null,2)+'\n');
