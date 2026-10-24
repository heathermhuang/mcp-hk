import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {test} from 'node:test';
import {AgentAuthService,digest,JWT_GRANT,CLAIM_GRANT,protectedDataPath,isAgentAuthPath,dataRequestHeaders} from './agent-auth.ts';

async function fixture(){
  const db=new DatabaseSync(':memory:');let now=Date.UTC(2026,9,19,12);
  const sql={exec(q,...v){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...v):(s.run(...v),[]);}};
  const atomic=fn=>{db.exec('BEGIN');try{const result=fn();db.exec('COMMIT');return result;}catch(error){db.exec('ROLLBACK');throw error;}};
  const service=new AgentAuthService(sql,'https://mcp.hk',atomic,()=>now);await service.init();
  const req=(path,data,extra={})=>service.handle(new Request('https://mcp.hk'+path,{method:data===undefined?'GET':'POST',headers:{'x-auth-client-key':'test-ip',...(data===undefined?{}:{'Content-Type':'application/json'}),...extra},body:data===undefined?undefined:JSON.stringify(data)}));
  const form=(path,data,extra={})=>service.handle(new Request('https://mcp.hk'+path,{method:'POST',headers:{'x-auth-client-key':'test-ip','Content-Type':'application/x-www-form-urlencoded',...extra},body:new URLSearchParams(data)}));
  const register=async()=>{const r=await req('/agent/identity',{type:'anonymous'});assert.equal(r.status,201);return r.json();};
  const exchange=async assertion=>{const r=await form('/oauth2/token',{grant_type:JWT_GRANT,assertion,resource:'https://mcp.hk/agent/data'});assert.equal(r.status,200,await r.clone().text());return r.json();};
  const owner=async()=>{const response=await form('/agent/account',{action:'create'},{Origin:'https://mcp.hk'});assert.equal(response.status,200);const html=await response.text();return {cookie:response.headers.get('Set-Cookie').split(';')[0],id:html.match(/Account ID: <code>([^<]+)/)[1],key:html.match(/<code>(recover_[^<]+)/)[1],csrf:html.match(/name="csrf" value="([^"]+)/)[1],html};};
  return {db,sql,atomic,service,req,form,register,exchange,owner,advance:s=>{now+=s*1000;}};
}
test('real anonymous registration, signed JWT exchange, protected read and immediate revocation',async()=>{
  const f=await fixture(),r=await f.register(),t=await f.exchange(r.identity_assertion);
  assert.deepEqual(r.pre_claim_scopes,['data.read']);assert.equal(t.expires_in,900);
  assert.equal((await f.req('/agent/data')).status,401);
  const authorized=await f.req('/agent/data',undefined,{Authorization:'Bearer '+t.access_token});assert.equal(authorized.status,200);assert.equal((await authorized.json()).registration_id,r.registration_id);
  assert.equal((await f.form('/oauth2/revoke',{token:t.access_token})).status,200);
  assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+t.access_token})).status,401);
  // Revoking an access token retains the registration assertion for standard refresh.
  assert.equal((await f.exchange(r.identity_assertion)).scope,'data.read');
  await f.form('/oauth2/revoke',{token:r.identity_assertion});
  assert.equal((await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:r.identity_assertion})).status,400);
  assert.equal((await f.form('/oauth2/revoke',{token:'unknown'})).status,200);
});
test('key persistence, public JWKS verification, token type/audience/signature and expiry boundaries',async()=>{
  const f=await fixture(),r=await f.register(),t=await f.exchange(r.identity_assertion);
  const jwks=await (await f.req('/oauth2/jwks')).json(),jwk=jwks.keys[0];assert.equal(jwk.d,undefined);
  const [h,p,s]=t.access_token.split('.'),key=await crypto.subtle.importKey('jwk',jwk,{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
  assert.equal(await crypto.subtle.verify({name:'ECDSA',hash:'SHA-256'},key,Buffer.from(s,'base64url'),Buffer.from(h+'.'+p)),true);
  const restarted=new AgentAuthService(f.sql,'https://mcp.hk',f.atomic,()=>Date.UTC(2026,9,19,12));await restarted.init();
  assert.equal((await restarted.handle(new Request('https://mcp.hk/agent/data',{headers:{Authorization:'Bearer '+t.access_token}}))).status,200);
  for(const invalid of [r.identity_assertion,t.access_token.slice(0,-8)+'AAAAAAAA',t.access_token+'.extra'])assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+invalid})).status,401);
  f.advance(901);assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+t.access_token})).status,401);
  f.advance(86400);assert.equal((await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:r.identity_assertion})).status,400);
});
test('claim binds only the selected account, rotates pre-claim credentials and supports owner revocation',async()=>{
  const f=await fixture(),r=await f.register(),old=await f.exchange(r.identity_assertion),owner=await f.owner(),other=await f.owner();
  const claim=await (await f.req('/agent/identity/claim',{claim_token:r.claim_token,owner_id:owner.id})).json();
  const attempt=new URL(claim.claim.verification_uri).searchParams.get('attempt');
  assert.equal((await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).status,400);
  assert.equal((await (await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).json()).error,'slow_down');
  const data={attempt,user_code:claim.claim.user_code,csrf:other.csrf};
  assert.equal((await f.form('/agent/claim',data,{Origin:'https://mcp.hk',Cookie:other.cookie})).status,403);
  data.csrf=owner.csrf;
  assert.equal((await f.form('/agent/claim',data,{Origin:'https://evil.test',Cookie:owner.cookie})).status,403);
  assert.equal((await f.form('/agent/claim',data,{Origin:'https://mcp.hk',Cookie:owner.cookie})).status,200);
  assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+old.access_token})).status,401);
  assert.equal((await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:r.identity_assertion})).status,400);
  f.advance(5);const granted=await (await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).json();assert.ok(granted.identity_assertion&&granted.access_token);
  assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+granted.access_token})).status,200);
  assert.equal((await f.form('/agent/account',{action:'revoke',registration:r.registration_id,csrf:other.csrf},{Origin:'https://mcp.hk',Cookie:other.cookie})).status,403);
  assert.equal((await f.form('/agent/account',{action:'revoke',registration:r.registration_id,csrf:owner.csrf},{Origin:'https://mcp.hk',Cookie:owner.cookie})).status,200);
  assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+granted.access_token})).status,401);
  const stored=JSON.stringify(f.db.prepare('SELECT * FROM auth_records').all());for(const secret of [owner.key,r.identity_assertion,old.access_token,r.claim_token,attempt])assert.equal(stored.includes(secret),false);
});
test('claim codes are guess-bounded, expire and cannot be claimed twice',async()=>{
  const f=await fixture(),r=await f.register(),owner=await f.owner();
  const c=await (await f.req('/agent/identity/claim',{claim_token:r.claim_token,owner_id:owner.id})).json();const attempt=new URL(c.claim.verification_uri).searchParams.get('attempt');
  for(let i=0;i<5;i++)assert.equal((await f.form('/agent/claim',{attempt,user_code:c.claim.user_code==='000000'?'111111':'000000',csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,403);
  assert.equal((await f.form('/agent/claim',{attempt,user_code:c.claim.user_code,csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,403);
  f.advance(601);assert.equal((await (await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).json()).error,'expired_token');
});
test('PKCE consent requires a signed-in owner, exact redirect and CSRF; codes are single use',async()=>{
  const f=await fixture(),owner=await f.owner(),verifier='v'.repeat(43),challenge=await digest(verifier),redirect='https://client.example/callback';
  const client=await (await f.req('/oauth2/register',{client_name:'Test <script>client</script>',redirect_uris:[redirect],token_endpoint_auth_method:'none'})).json();
  const data={client_id:client.client_id,redirect_uri:redirect,response_type:'code',code_challenge:challenge,code_challenge_method:'S256',state:'opaque-state',scope:'data.read'};
  const html=await (await f.req('/oauth2/authorize?'+new URLSearchParams(data),undefined,{Cookie:owner.cookie})).text();assert.ok(html.includes('&lt;script&gt;'));assert.equal(html.includes('<script>'),false);
  assert.equal((await f.form('/oauth2/authorize',{...data,csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://evil.test'})).status,403);
  assert.equal((await f.form('/oauth2/authorize',{...data,csrf:owner.csrf,redirect_uri:'https://evil.test/'},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,400);
  const accepted=await f.form('/oauth2/authorize',{...data,csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'});assert.equal(accepted.status,303);const location=new URL(accepted.headers.get('Location'));assert.equal(location.searchParams.get('state'),'opaque-state');
  const tokenData={grant_type:'authorization_code',code:location.searchParams.get('code'),client_id:client.client_id,redirect_uri:redirect,code_verifier:verifier};
  assert.equal((await f.form('/oauth2/token',{...tokenData,code_verifier:'x'.repeat(43)})).status,400);
  const concurrent=await Promise.all([f.form('/oauth2/token',tokenData),f.form('/oauth2/token',tokenData)]);assert.deepEqual(concurrent.map(r=>r.status).sort(),[200,400]);
  for(const invalid of ['http://evil.test/cb','https://client.example/#fragment','https://user:password@client.example/'])assert.equal((await f.req('/oauth2/register',{redirect_uris:[invalid]})).status,400);
});
test('metadata only advertises implemented flows, body/scope bounds and durable registration caps',async()=>{
  const f=await fixture(),metadata=await (await f.req('/.well-known/oauth-authorization-server')).json();
  assert.deepEqual(metadata.agent_auth.identity_types_supported,['anonymous']);assert.equal(metadata.issuer,'https://mcp.hk');assert.equal(metadata.agent_auth.register_uri,'https://mcp.hk/agent/identity');
  const resource=await (await f.req('/.well-known/oauth-protected-resource')).json();assert.equal(resource.resource,'https://mcp.hk');assert.deepEqual(resource.scopes_supported,['data.read']);
  const pathResource=await (await f.req('/.well-known/oauth-protected-resource/agent/data')).json();assert.equal(pathResource.resource,'https://mcp.hk/agent/data');
  const unauthorized=await f.req('/agent/data');assert.match(unauthorized.headers.get('WWW-Authenticate'),/resource_metadata/);
  assert.equal((await f.req('/agent/identity',{type:'identity_assertion'})).status,400);
  assert.equal((await f.req('/agent/identity',{type:'anonymous',scope:'admin'})).status,400);
  assert.equal((await f.req('/agent/identity',{type:'anonymous',name:'x'.repeat(9000)})).status,413);
  for(let i=0;i<5;i++)await f.register();assert.equal((await f.req('/agent/identity',{type:'anonymous'})).status,429);
  f.advance(3600);assert.equal((await f.req('/agent/identity',{type:'anonymous'})).status,201);
  assert.equal(protectedDataPath('/agent/data/__ops/snapshot'),undefined);assert.equal(protectedDataPath('/agent/data/packs'),'/api/v1/packs');assert.equal(isAgentAuthPath('/__ops/status'),false);
  assert.equal((await f.req('/agent/data/__ops/status')).status,404);assert.equal((await f.req('/agent/data',{})).status,405);
});
test('root and path discovery issue usable audience-bound read tokens; unrelated audiences stay rejected',async()=>{
  const f=await fixture(),reg=await f.register();
  for(const path of ['/.well-known/oauth-protected-resource','/.well-known/oauth-protected-resource/agent/data']){
    const metadata=await (await f.req(path)).json();const response=await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:reg.identity_assertion,resource:metadata.resource});assert.equal(response.status,200);
    const token=(await response.json()).access_token;assert.equal(JSON.parse(Buffer.from(token.split('.')[1],'base64url')).aud,metadata.resource);
    assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+token})).status,200);
    await f.form('/oauth2/revoke',{token});assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+token})).status,401);
  }
  assert.equal((await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:reg.identity_assertion,resource:'https://mcp.hk/__ops'})).status,400);
});
test('owner recovery and logout authenticate without collecting a user identity',async()=>{
  const f=await fixture(),owner=await f.owner();
  const signed=await f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'});assert.equal(signed.status,200);assert.match(signed.headers.get('Set-Cookie'),/Secure; HttpOnly; SameSite=Strict/);
  // no-referrer turns basic form POST Origin into null in browsers. strict-origin
  // preserves CSRF's Origin check while excluding private paths/query strings.
  assert.equal(signed.headers.get('Referrer-Policy'),'strict-origin');
  assert.equal((await f.form('/agent/account',{action:'create'},{Origin:'https://evil.test'})).status,403);
  const signedHtml=await signed.text(),csrf=signedHtml.match(/name="csrf" value="([^"]+)/)[1],cookie=signed.headers.get('Set-Cookie').split(';')[0];
  const logout=await f.form('/agent/account',{action:'logout',csrf},{Cookie:cookie,Origin:'https://mcp.hk'});assert.equal(logout.status,200);assert.match(logout.headers.get('Set-Cookie'),/Max-Age=0/);
  assert.equal((await f.form('/agent/account',{action:'revoke',registration:'unknown',csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,403);
});
test('bulk revocation survives a service restart and never invalidates unrelated public routes',async()=>{
  const f=await fixture(),a=await f.register(),b=await f.register(),ta=await f.exchange(a.identity_assertion),tb=await f.exchange(b.identity_assertion);
  assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+ta.access_token})).status,200);
  f.service.revokeAll();const restarted=new AgentAuthService(f.sql,'https://mcp.hk',f.atomic,()=>Date.UTC(2026,9,19,12));await restarted.init();
  for(const token of [ta.access_token,tb.access_token])assert.equal((await restarted.handle(new Request('https://mcp.hk/agent/data',{headers:{Authorization:'Bearer '+token}}))).status,401);
  assert.equal(isAgentAuthPath('/api/v1/packs'),false);assert.equal(isAgentAuthPath('/mcp'),false);
});
test('valid signatures cannot override token audience, type, scope or registration version',async()=>{
  const f=await fixture(),r=await f.register(),t=await f.exchange(r.identity_assertion),[h,p]=t.access_token.split('.');
  const jwk=JSON.parse(f.db.prepare("SELECT value FROM auth_records WHERE kind='key'").get().value),key=await crypto.subtle.importKey('jwk',jwk,{name:'ECDSA',namedCurve:'P-256'},false,['sign']);
  for(const changes of [{aud:'https://evil.test'},{scope:'admin'},{v:99},{iss:'https://evil.test'}]){
    const payload={...JSON.parse(Buffer.from(p,'base64url')), ...changes},data=h+'.'+Buffer.from(JSON.stringify(payload)).toString('base64url');
    const token=data+'.'+Buffer.from(await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},key,Buffer.from(data))).toString('base64url');
    assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+token})).status,401);
  }
});
test('a failed revocation write reports failure without exposing storage errors or claiming success',async()=>{
  const f=await fixture(),r=await f.register(),t=await f.exchange(r.identity_assertion),original=f.sql.exec;
  f.sql.exec=(q,...args)=>{if(q==='DELETE FROM auth_records WHERE kind=? AND id=?')throw new Error('private backend details');return original(q,...args);};
  const failed=await f.form('/oauth2/revoke',{token:t.access_token});assert.equal(failed.status,503);assert.equal((await failed.json()).error,'temporarily_unavailable');
  f.sql.exec=original;assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+t.access_token})).status,200);
  await f.form('/oauth2/revoke',{token:t.access_token});assert.equal((await f.req('/agent/data',undefined,{Authorization:'Bearer '+t.access_token})).status,401);
});
test('both public and protected data forwarding omit credentials and retain the actual caller quota identity',()=>{
  const headers=dataRequestHeaders(new Request('https://mcp.hk/api/v1/packs',{headers:{Authorization:'Bearer private-token',Cookie:'__Host-mcp_owner=private-session','x-auth-client-key':'forged-auth-key','x-mcp-client-ip':'forged-ip','cf-connecting-ip':'203.0.113.8',Accept:'application/json','Mcp-Session-Id':'public-mcp-session'}}));
  for(const name of ['Authorization','Cookie','x-auth-client-key'])assert.equal(headers.has(name),false);
  assert.equal(headers.get('x-mcp-client-ip'),'203.0.113.8');assert.equal(headers.get('Mcp-Session-Id'),'public-mcp-session');assert.equal(headers.get('Accept'),'application/json');
  const controller=dataRequestHeaders(new Request('https://mcp.hk/api/v1/packs',{headers:{Cookie:'owner-secret',Authorization:'Bearer owner-secret','x-mcp-client-ip':'203.0.113.8'}}),'203.0.113.8');
  assert.equal(controller.get('x-mcp-client-ip'),'203.0.113.8');assert.equal(controller.has('Cookie'),false);assert.equal(controller.has('Authorization'),false);
});

function accountResponse(response,html){return {cookie:response.headers.get('Set-Cookie').split(';')[0],key:html.match(/<code>(recover_[^<]+)/)[1],csrf:html.match(/name="csrf" value="([^"]+)/)[1]};}
test('recovery race consumes key once and invalidates both clients pre-rotation account actions across restart',async()=>{
  const f=await fixture(),owner=await f.owner();
  // Two distinct valid stored cookies model clients already signed in before recovery.
  const original=f.db.prepare("SELECT value,expires FROM auth_records WHERE kind='session'").get();
  const otherToken='synthetic-second-client',otherCookie='__Host-mcp_owner='+otherToken;
  f.db.prepare('INSERT INTO auth_records VALUES (?,?,?,?)').run('session',await digest(otherToken),original.value,original.expires);
  for(const cookie of [owner.cookie,otherCookie])assert.match(await (await f.req('/agent/account',undefined,{Cookie:cookie})).text(),/Account ID:/);
  f.advance(1800);
  const expiry=f.db.prepare("SELECT expires FROM auth_records WHERE kind='owner'").get().expires;
  const race=await Promise.all([f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'}),f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'})]);
  assert.deepEqual(race.map(r=>r.status).sort(),[200,401]);
  const won=race.find(r=>r.status===200),fresh=accountResponse(won,await won.text());
  for(const cookie of [owner.cookie,otherCookie])assert.equal((await f.form('/agent/account',{action:'rotate',csrf:owner.csrf},{Origin:'https://mcp.hk',Cookie:cookie})).status,403);
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'})).status,401);
  assert.equal(f.db.prepare("SELECT expires FROM auth_records WHERE kind='owner'").get().expires,expiry);
  const restarted=new AgentAuthService(f.sql,'https://mcp.hk',f.atomic,()=>Date.UTC(2026,9,19,12,30));await restarted.init();
  for(const cookie of [owner.cookie,otherCookie])assert.equal((await restarted.handle(new Request('https://mcp.hk/agent/account',{method:'POST',headers:{Origin:'https://mcp.hk',Cookie:cookie,'Content-Type':'application/json'},body:JSON.stringify({action:'rotate',csrf:owner.csrf})}))).status,403);
  // If the key body was lost but the cookie arrived, explicit rotation recovers.
  const rotated=await f.form('/agent/account',{action:'rotate',csrf:fresh.csrf},{Origin:'https://mcp.hk',Cookie:fresh.cookie});assert.equal(rotated.status,200);
  const next=accountResponse(rotated,await rotated.text());
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:fresh.key},{Origin:'https://mcp.hk'})).status,401);
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:next.key},{Origin:'https://mcp.hk'})).status,200);
  const audit=JSON.stringify(f.db.prepare("SELECT value FROM auth_records WHERE kind='audit'").all());
  for(const secret of [owner.key,owner.cookie,owner.csrf,fresh.key,next.key,otherToken])assert.equal(audit.includes(secret),false);
  for(const event of ['owner.created','owner.recovered','owner.rotated'])assert.ok(audit.includes(event));
});
test('legacy sessions fail closed; legacy owner recovery migrates without extending expiry; failed rotation rolls back',async()=>{
  const f=await fixture(),owner=await f.owner();
  f.db.exec("UPDATE auth_records SET value=json_remove(value,'$.generation') WHERE kind IN ('owner','session')");
  assert.equal((await f.form('/agent/account',{action:'rotate',csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,403);
  const expiry=f.db.prepare("SELECT expires FROM auth_records WHERE kind='owner'").get().expires;
  const original=f.sql.exec;
  f.sql.exec=(q,...args)=>{if(q==='INSERT OR REPLACE INTO auth_records VALUES (?,?,?,?)'&&args[0]==='audit'&&args[2].includes('owner.recovered'))throw new Error('synthetic write failure');return original(q,...args);};
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'})).status,503);
  f.sql.exec=original;
  const response=await f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'});assert.equal(response.status,200);
  const migrated=accountResponse(response,await response.text());
  assert.equal(f.db.prepare("SELECT expires FROM auth_records WHERE kind='owner'").get().expires,expiry);
  f.advance(90*86400);
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:migrated.key},{Origin:'https://mcp.hk'})).status,401);
});
test('scoped containment destroys recovery, sessions, pending claims and issued authorization artifacts; other owner survives',async()=>{
  const f=await fixture(),owner=await f.owner(),other=await f.owner(),r=await f.register();
  const c=await (await f.req('/agent/identity/claim',{claim_token:r.claim_token,owner_id:owner.id})).json(),attempt=new URL(c.claim.verification_uri).searchParams.get('attempt');
  assert.equal((await f.form('/agent/claim',{attempt,user_code:c.claim.user_code,csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'})).status,200);
  const granted=await (await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).json();assert.ok(granted.access_token);
  const pending=await f.register(),claim=await (await f.req('/agent/identity/claim',{claim_token:pending.claim_token,owner_id:owner.id})).json();assert.ok(claim.claim);
  f.service.containOwner(owner.id);
  const restarted=new AgentAuthService(f.sql,'https://mcp.hk',f.atomic,()=>Date.UTC(2026,9,19,12));await restarted.init();
  assert.equal((await restarted.handle(new Request('https://mcp.hk/agent/data',{headers:{Authorization:'Bearer '+granted.access_token}}))).status,401);
  assert.equal((await f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:granted.identity_assertion})).status,400);
  assert.equal((await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:pending.claim_token})).status,400);
  assert.equal((await f.form('/agent/account',{action:'login',recovery_key:owner.key},{Origin:'https://mcp.hk'})).status,401);
  assert.equal((await f.form('/agent/account',{action:'rotate',csrf:owner.csrf},{Origin:'https://mcp.hk',Cookie:owner.cookie})).status,403);
  assert.equal((await f.form('/agent/account',{action:'rotate',csrf:other.csrf},{Origin:'https://mcp.hk',Cookie:other.cookie})).status,200);
  assert.equal(f.db.prepare("SELECT count(*) n FROM auth_records WHERE kind='attempt'").get().n,0);
});

test('containment during asynchronous signing cannot issue a surviving owner token',async()=>{
  const f=await fixture(),owner=await f.owner(),r=await f.register();
  const claim=await (await f.req('/agent/identity/claim',{claim_token:r.claim_token,owner_id:owner.id})).json();
  const attempt=new URL(claim.claim.verification_uri).searchParams.get('attempt');
  await f.form('/agent/claim',{attempt,user_code:claim.claim.user_code,csrf:owner.csrf},{Cookie:owner.cookie,Origin:'https://mcp.hk'});
  const granted=await (await f.form('/oauth2/token',{grant_type:CLAIM_GRANT,claim_token:r.claim_token})).json();
  const original=crypto.subtle.sign.bind(crypto.subtle);let arrive,release;
  const reached=new Promise(r=>{arrive=r;}),resume=new Promise(r=>{release=r;});
  crypto.subtle.sign=async(...args)=>{arrive();await resume;return original(...args);};
  try{
    const inflight=f.form('/oauth2/token',{grant_type:JWT_GRANT,assertion:granted.identity_assertion});
    await reached;f.service.containOwner(owner.id);release();
    assert.equal((await inflight).status,400);
    assert.equal(f.db.prepare("SELECT count(*) n FROM auth_records WHERE kind='at+jwt'").get().n,0);
  }finally{release();crypto.subtle.sign=original;}
});
