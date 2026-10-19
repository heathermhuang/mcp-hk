// Explicit synthetic-account smoke. Raw credentials go only to an owner-only file.
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {dirname} from 'node:path';
import {parseArgs} from 'node:util';
const {values}=parseArgs({options:{origin:{type:'string'},receipt:{type:'string'},credentials:{type:'string'},'public-data':{type:'boolean'},'leave-browser-session':{type:'boolean'}}});
const origin=values.origin||'http://127.0.0.1:8878',url=new URL(origin);
assert.ok((url.protocol==='https:'&&url.hostname==='mcp.hk')||(url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname)));
assert.equal(url.origin,origin);assert.ok(values.receipt&&values.credentials);
const steps=[],privateState={},grant='urn:ietf:params:oauth:grant-type:jwt-bearer',claimGrant='urn:workos:agent-auth:grant-type:claim';
async function call(path,{data,form,headers={},expected=200}={}) {
  const response=await fetch(origin+path,{method:data||form?'POST':'GET',headers:{...(data?{'Content-Type':'application/json'}:form?{'Content-Type':'application/x-www-form-urlencoded'}:{}),...headers},body:data?JSON.stringify(data):form?new URLSearchParams(form):undefined,redirect:'manual',signal:AbortSignal.timeout(180000)});
  const reader=response.body?.getReader();let text='',bytes=0;const decoder=new TextDecoder();
  if(reader)for(;;){const p=await reader.read();if(p.done)break;bytes+=p.value.length;if(bytes>100000){await reader.cancel();throw new Error('Oversized smoke response');}text+=decoder.decode(p.value,{stream:true});}
  assert.equal(response.status,expected,'Unexpected HTTP status for '+path.split('?')[0]);
  steps.push({path:path.split('?')[0],status:response.status});let json;try{json=JSON.parse(text);}catch{}
  return {response,text,json};
}
const hash=async s=>Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))).toString('base64url');
const bearer=token=>({Authorization:'Bearer '+token});
const exchange=async assertion=>(await call('/oauth2/token',{form:{grant_type:grant,assertion,resource:origin+'/agent/data'}})).json;
try {
  const metadata=(await call('/.well-known/oauth-authorization-server')).json;
  assert.equal(metadata.issuer,origin);assert.deepEqual(metadata.agent_auth.identity_types_supported,['anonymous']);
  const resource=(await call('/.well-known/oauth-protected-resource')).json;assert.equal(resource.resource,origin+'/agent/data');
  const jwks=(await call('/oauth2/jwks')).json;assert.equal(jwks.keys[0].d,undefined);
  await call('/agent/data',{expected:401});
  const registration=(await call('/agent/identity',{data:{type:'anonymous',scopes:['data.read'],name:'Synthetic release verification'},expected:201})).json;
  Object.assign(privateState,{registration});let tokens=await exchange(registration.identity_assertion);
  const [h,p,s]=tokens.access_token.split('.'),key=await crypto.subtle.importKey('jwk',jwks.keys[0],{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
  assert.equal(await crypto.subtle.verify({name:'ECDSA',hash:'SHA-256'},key,Buffer.from(s,'base64url'),Buffer.from(h+'.'+p)),true);
  assert.equal(JSON.parse(Buffer.from(p,'base64url')).aud,origin+'/agent/data');
  await call('/agent/data',{headers:bearer(tokens.access_token)});
  if(values['public-data']) {
    const packs=await call('/agent/data/packs',{headers:bearer(tokens.access_token)});assert.ok(packs.json&&packs.text.length>100);
    const catalogue=await call('/agent/data/catalogue/datasets?q=public%20holidays&limit=2&access=all',{headers:bearer(tokens.access_token)});assert.ok(catalogue.json&&catalogue.text.includes('data'));
    await call('/api/v1/packs'); // Existing anonymous data remains available.
  }
  await call('/oauth2/revoke',{form:{token:tokens.access_token}});await call('/agent/data',{headers:bearer(tokens.access_token),expected:401});
  tokens=await exchange(registration.identity_assertion);
  const account=await call('/agent/account',{form:{action:'create'},headers:{Origin:origin}});
  const cookie=account.response.headers.get('Set-Cookie').split(';')[0],owner=account.text.match(/Account ID: <code>([^<]+)/)[1],recovery=account.text.match(/<code>(recover_[^<]+)/)[1],csrf=account.text.match(/name="csrf" value="([^"]+)/)[1];
  Object.assign(privateState,{owner,recovery,cookie,csrf});
  const claim=(await call('/agent/identity/claim',{data:{claim_token:registration.claim_token,owner_id:owner}})).json;
  await call(new URL(claim.claim.verification_uri).pathname+new URL(claim.claim.verification_uri).search,{headers:{Cookie:cookie}});
  const pending=await call('/oauth2/token',{form:{grant_type:claimGrant,claim_token:registration.claim_token},expected:400});assert.equal(pending.json.error,'authorization_pending');const pendingAt=Date.now();
  await call('/agent/claim',{form:{attempt:new URL(claim.claim.verification_uri).searchParams.get('attempt'),user_code:claim.claim.user_code,csrf},headers:{Cookie:cookie,Origin:origin}});
  await call('/agent/data',{headers:bearer(tokens.access_token),expected:401});
  await new Promise(resolve=>setTimeout(resolve,Math.max(0,5100-(Date.now()-pendingAt))));
  const claimed=(await call('/oauth2/token',{form:{grant_type:claimGrant,claim_token:registration.claim_token}})).json;
  await call('/agent/data',{headers:bearer(claimed.access_token)});
  await call('/agent/account',{form:{action:'revoke',registration:registration.registration_id,csrf},headers:{Cookie:cookie,Origin:origin}});
  await call('/agent/data',{headers:bearer(claimed.access_token),expected:401});
  const redirect='https://example.invalid/mcp-hk-auth-smoke',verifier=crypto.randomUUID()+crypto.randomUUID(),challenge=await hash(verifier);
  const client=(await call('/oauth2/register',{data:{client_name:'Synthetic browser verification',redirect_uris:[redirect],token_endpoint_auth_method:'none'},expected:201})).json;
  const authorization={client_id:client.client_id,redirect_uri:redirect,response_type:'code',code_challenge:challenge,code_challenge_method:'S256',scope:'data.read',state:crypto.randomUUID()};
  await call('/oauth2/authorize?'+new URLSearchParams(authorization),{headers:{Cookie:cookie}});
  const consent=await call('/oauth2/authorize',{form:{...authorization,csrf},headers:{Cookie:cookie,Origin:origin},expected:303});
  const location=new URL(consent.response.headers.get('Location'));assert.equal(location.origin,'https://example.invalid');assert.equal(location.searchParams.get('state'),authorization.state);
  const tokenForm={grant_type:'authorization_code',client_id:client.client_id,redirect_uri:redirect,code:location.searchParams.get('code'),code_verifier:verifier};
  const oauth=(await call('/oauth2/token',{form:tokenForm})).json;await call('/oauth2/token',{form:tokenForm,expected:400});
  const granted=(await call('/agent/data',{headers:bearer(oauth.access_token)})).json;
  Object.assign(privateState,{browserRegistration:granted.registration_id,browserAccessToken:oauth.access_token});
  if(!values['leave-browser-session']){await call('/agent/account',{form:{action:'revoke',registration:granted.registration_id,csrf},headers:{Cookie:cookie,Origin:origin}});await call('/agent/data',{headers:bearer(oauth.access_token),expected:401});}
  await mkdir(dirname(values.credentials),{recursive:true,mode:0o700});await writeFile(values.credentials,JSON.stringify(privateState),{mode:0o600});
  const receipt={checkedAt:new Date().toISOString(),origin,passed:true,flows:['anonymous registration','ES256/JWKS verification','JWT bearer exchange','protected resource','immediate access-token revocation','owner account','claim approval and credential rotation','owner registration revocation','PKCE consent and code exchange','single-use code'],publicDataRead:Boolean(values['public-data']),browserContinuation:Boolean(values['leave-browser-session']),steps};
  await mkdir(dirname(values.receipt),{recursive:true});await writeFile(values.receipt,JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({passed:true,requests:steps.length,publicDataRead:receipt.publicDataRead,browserContinuation:receipt.browserContinuation}));
} catch(error) {
  // Never print response bodies, JWTs, claim links, cookies or recovery keys.
  console.error('Auth smoke failed:',error instanceof Error?error.message:'unknown error');process.exitCode=1;
}
