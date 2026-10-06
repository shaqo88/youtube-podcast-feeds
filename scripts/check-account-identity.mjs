import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {googleAccountCall} from '../workers/accounts/src/auth.mjs';

const environment=process.env.ACCOUNTS_ENVIRONMENT;
assert.ok(['preview','production'].includes(environment),'Choose an account environment');
const config=JSON.parse(readFileSync(`config/accounts.${environment}.json`));
assert.ok(config.firebase?.projectId,'Configure Firebase before checking its identity service');
const credential=JSON.parse(process.env.GOOGLE_ACCOUNT_SERVICE_JSON||'{}');
assert.equal(credential.project_id,config.firebase.projectId,'Wrong account service project');
assert.equal(credential.client_email,`account-lifecycle@${config.firebase.projectId}.iam.gserviceaccount.com`,'Use the dedicated lifecycle identity');
const result=await googleAccountCall({FIREBASE_PROJECT_ID:config.firebase.projectId,GOOGLE_ACCOUNT_SERVICE_JSON:process.env.GOOGLE_ACCOUNT_SERVICE_JSON},'lookup',{localId:[`readiness-${randomUUID()}`]});
assert.equal(result.users?.length||0,0,'Unexpected readiness lookup result');
console.log(JSON.stringify({environment,serviceOAuthAndLookupVerified:true}));
