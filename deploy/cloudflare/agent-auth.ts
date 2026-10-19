// Optional hosted agent access. Public MCP and /api/v1 remain anonymous.
// The separate auth DO owns keys, registrations and revocation, never data backups.
export const READ_SCOPE = 'data.read';
export const JWT_GRANT = 'urn:ietf:params:oauth:grant-type:jwt-bearer';
export const CLAIM_GRANT = 'urn:workos:agent-auth:grant-type:claim';
const encoder = new TextEncoder();
type RecordValue = Record<string, unknown>;
type Registration = {id: string; owner: string; version: number; expires: number; revoked: boolean; name: string};
type Claim = {registration: string; owner: string; attempt: string; code: string; expires: number; tries: number; poll: number; consumed: boolean};
type Session = {owner: string; csrf: string};
type Client = {name: string; redirects: string[]};
type Code = {registration: string; client: string; redirect: string; challenge: string};
class AuthError extends Error {
  code: string;
  status: number;
  constructor(code: string, status = 400) {super(code);this.code=code;this.status=status;}
}
function random(prefix = ''): string {return prefix + base64(crypto.getRandomValues(new Uint8Array(32)));}
function userCode(): string {
  let n: number;do{n=crypto.getRandomValues(new Uint32Array(1))[0];}while(n>=4294000000);
  return String(n%1000000).padStart(6,'0');
}
function base64(bytes: Uint8Array): string {return btoa(String.fromCharCode(...bytes)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');}
function decode(value: string): Uint8Array {return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4-value.length%4)%4)), c=>c.charCodeAt(0));}
export async function digest(value: string): Promise<string> {return base64(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))));}
function escape(value: string): string {return value.replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));}
const commonHeaders = {'Cache-Control':'no-store', 'Pragma':'no-cache', 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'no-referrer', 'X-Robots-Tag':'noindex, nofollow', 'Strict-Transport-Security':'max-age=31536000'};
function json(value: unknown, status = 200, headers: Record<string,string> = {}): Response {
  return Response.json(value, {status, headers:{...commonHeaders,'Access-Control-Allow-Origin':'*',...headers}});
}
function page(title: string, body: string, headers: Record<string,string> = {}): Response {
  return new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} — mcp.hk</title><style>body{font:17px/1.6 system-ui;background:#0b1419;color:#e7f1f4;margin:0}main{max-width:660px;margin:5vh auto;padding:32px}a{color:#79ded0}label{display:block;margin-top:20px}input,button{box-sizing:border-box;font:inherit;padding:12px;margin:8px 0;max-width:100%}input{width:100%;background:#14242c;color:inherit;border:1px solid #69818b;border-radius:6px}button{background:#9ee8b9;border:0;border-radius:6px;color:#11241d;cursor:pointer}code{overflow-wrap:anywhere}section{border-top:1px solid #39515c;padding:16px 0}small{color:#b6c7cd}</style></head><body><main><a href="/">mcp.hk</a><h1>${escape(title)}</h1><p>Optional read-only agent access. Public data and MCP remain available without an account.</p>${body}<p><a href="/auth.md">Agent setup</a> · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></p></main></body></html>`,{headers:{...commonHeaders,'Content-Type':'text/html; charset=utf-8','Referrer-Policy':'strict-origin','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",...headers}});
}
function scope(value: unknown): void {
  if (value === undefined || value === '') return;
  const values = Array.isArray(value) ? value : typeof value === 'string' ? value.split(' ') : [];
  if (!values.length || values.some(s=>s !== READ_SCOPE)) throw new AuthError('invalid_scope');
}
async function body(request: Request): Promise<RecordValue> {
  if (Number(request.headers.get('Content-Length')) > 8192) throw new AuthError('invalid_request',413);
  const reader = request.body?.getReader(); const chunks: Uint8Array[]=[]; let size=0;
  if (reader) for (;;) {const part=await reader.read(); if(part.done)break;size+=part.value.length;if(size>8192){await reader.cancel();throw new AuthError('invalid_request',413);}chunks.push(part.value);}
  const bytes=new Uint8Array(size);let offset=0;for(const part of chunks){bytes.set(part,offset);offset+=part.length;}
  const text=new TextDecoder('utf-8',{fatal:true,ignoreBOM:false}).decode(bytes);
  if (request.headers.get('Content-Type')?.split(';')[0] === 'application/json') {
    const value:unknown=JSON.parse(text);if(!value || typeof value!=='object' || Array.isArray(value))throw new AuthError('invalid_request');return value as RecordValue;
  }
  if(request.headers.get('Content-Type')?.split(';')[0]!=='application/x-www-form-urlencoded')throw new AuthError('invalid_request',415);
  const params=new URLSearchParams(text);const result:RecordValue={};for(const [k,v] of params){if(k in result)throw new AuthError('invalid_request');result[k]=v;}return result;
}
function field(value: unknown, max=4096): string {if(typeof value!=='string'||!value||value.length>max)throw new AuthError('invalid_request');return value;}
export function isAgentAuthPath(path: string): boolean {
  return path.startsWith('/agent/') || path.startsWith('/oauth2/') || path==='/.well-known/oauth-authorization-server' || path==='/.well-known/oauth-protected-resource' || path==='/.well-known/oauth-protected-resource/agent/data';
}
export function protectedDataPath(path: string): string | undefined {
  return ({'/agent/data/packs':'/api/v1/packs','/agent/data/catalogue/datasets':'/api/v1/catalogue/datasets','/agent/data/status':'/api/v1/status'} as Record<string,string>)[path];
}
export function dataRequestHeaders(request: Request): Headers {
  const headers=new Headers(request.headers);
  headers.delete('Authorization');headers.delete('Cookie');headers.delete('x-auth-client-key');
  headers.set('x-mcp-client-ip',request.headers.get('cf-connecting-ip')||'unknown');
  return headers;
}

export class AgentAuthService {
  private sql: Pick<SqlStorage,'exec'>;
  readonly origin: string;
  private clock: ()=>number;
  private privateKey!: CryptoKey;
  private publicKey!: CryptoKey;
  private jwk!: JsonWebKey;
  private kid!: string;
  constructor(sql: Pick<SqlStorage,'exec'>, origin: string, clock = ()=>Date.now()) {
    this.sql=sql;this.origin=origin;this.clock=clock;
    this.sql.exec('CREATE TABLE IF NOT EXISTS auth_records (kind TEXT NOT NULL, id TEXT NOT NULL, value TEXT NOT NULL, expires INTEGER NOT NULL, PRIMARY KEY(kind,id))');
    this.sql.exec('CREATE INDEX IF NOT EXISTS auth_expiry ON auth_records(expires)');
  }
  now(): number {return Math.floor(this.clock()/1000);}
  private get<T>(kind: string,id: string): T | undefined {
    const row=Array.from(this.sql.exec('SELECT value FROM auth_records WHERE kind=? AND id=? AND expires>?',kind,id,this.now()))[0];return row ? JSON.parse(String(row.value)) as T : undefined;
  }
  private put(kind: string,id: string,value: unknown,expires: number): void {this.sql.exec('INSERT OR REPLACE INTO auth_records VALUES (?,?,?,?)',kind,id,JSON.stringify(value),expires);}
  private remove(kind: string,id: string): void {this.sql.exec('DELETE FROM auth_records WHERE kind=? AND id=?',kind,id);}
  cleanup(): void {this.sql.exec('DELETE FROM auth_records WHERE expires<=?',this.now());}
  revokeAll(): void {
    this.sql.exec("UPDATE auth_records SET value=json_set(value,'$.revoked',json('true'),'$.version',json_extract(value,'$.version')+1) WHERE kind='registration'");
    this.audit('registrations.revoked');
  }
  hasExpiringRecords(): boolean {return Boolean(Array.from(this.sql.exec("SELECT id FROM auth_records WHERE kind!='key' LIMIT 1")).length);}
  private audit(event: string,registration=''): void {this.put('audit',random(),{event,registration,at:this.now()},this.now()+7*86400);}
  async init(): Promise<void> {
    const stored=this.get<JsonWebKey>('key','signing');
    if(stored) {
      this.privateKey=await crypto.subtle.importKey('jwk',stored,{name:'ECDSA',namedCurve:'P-256'},false,['sign']);
      const {d: _private,...pub}=stored; this.jwk={...pub,key_ops:['verify']};
    } else {
      const pair=await crypto.subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},true,['sign','verify']);
      if(!('privateKey' in pair))throw new Error('Expected ECDSA key pair');
      this.privateKey=pair.privateKey;this.jwk=await crypto.subtle.exportKey('jwk',pair.publicKey) as JsonWebKey;
      this.put('key','signing',await crypto.subtle.exportKey('jwk',pair.privateKey),253402300799);
    }
    this.publicKey=await crypto.subtle.importKey('jwk',this.jwk,{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
    this.kid=(await digest(JSON.stringify({crv:this.jwk.crv,x:this.jwk.x,y:this.jwk.y,kty:this.jwk.kty}))).slice(0,24);
  }
  private limit(key: string,max: number,window: number): void {
    const id=key+':'+Math.floor(this.now()/window),old=this.get<number>('rate',id)||0;
    if(old>=max)throw new AuthError('rate_limited',429);this.put('rate',id,old+1,(Math.floor(this.now()/window)+1)*window);
  }
  private registration(id: string): Registration {
    const r=this.get<Registration>('registration',id);if(!r||r.revoked)throw new AuthError('invalid_grant');return r;
  }
  private async sign(reg: Registration,typ: string,aud: string,ttl: number): Promise<string> {
    const payload={iss:this.origin,sub:reg.id,aud,iat:this.now(),exp:this.now()+ttl,jti:random(),scope:READ_SCOPE,v:reg.version};
    const signing=base64(encoder.encode(JSON.stringify({alg:'ES256',typ,kid:this.kid})))+'.'+base64(encoder.encode(JSON.stringify(payload)));
    const signature=await crypto.subtle.sign({name:'ECDSA',hash:'SHA-256'},this.privateKey,encoder.encode(signing));
    this.put(typ,payload.jti,{registration:reg.id},payload.exp);return signing+'.'+base64(new Uint8Array(signature));
  }
  private async verify(token: string,typ: string,aud: string): Promise<{reg: Registration; jti: string}> {
    let claims: {sub:string;jti:string;version:unknown};
    try {
      if(token.length>4096)throw new Error();const parts=token.split('.');if(parts.length!==3)throw new Error();
      const h=JSON.parse(new TextDecoder().decode(decode(parts[0]))),p=JSON.parse(new TextDecoder().decode(decode(parts[1])));
      if(h.alg!=='ES256'||h.typ!==typ||h.kid!==this.kid||p.iss!==this.origin||p.aud!==aud||typeof p.exp!=='number'||p.exp<=this.now()||typeof p.iat!=='number'||p.iat>this.now()+30||p.scope!==READ_SCOPE||typeof p.sub!=='string'||typeof p.jti!=='string')throw new Error();
      if(!await crypto.subtle.verify({name:'ECDSA',hash:'SHA-256'},this.publicKey,decode(parts[2]),encoder.encode(parts[0]+'.'+parts[1])))throw new Error();
      claims={sub:p.sub,jti:p.jti,version:p.v};
    } catch {throw new AuthError('invalid_grant');}
    // Storage failures must remain failures, especially during revocation.
    const r=this.registration(claims.sub),entry=this.get<{registration:string}>(typ,claims.jti);
    if(claims.version!==r.version||entry?.registration!==r.id)throw new AuthError('invalid_grant');return {reg:r,jti:claims.jti};
  }
  private async assertion(reg: Registration): Promise<RecordValue> {
    const ttl=Math.min(86400,reg.expires-this.now());if(ttl<=0)throw new AuthError('invalid_grant');
    return {identity_assertion:await this.sign(reg,'oauth-id-jag+jwt',this.origin,ttl),assertion_expires:new Date((this.now()+ttl)*1000).toISOString()};
  }
  private async access(reg: Registration): Promise<RecordValue> {
    const ttl=Math.min(900,reg.expires-this.now());if(ttl<=0)throw new AuthError('invalid_grant');
    const token=await this.sign(reg,'at+jwt',this.origin+'/agent/data',ttl);
    // Signing awaits crypto; recheck durable revocation/version after it completes.
    const current=this.registration(reg.id);if(current.version!==reg.version)throw new AuthError('invalid_grant');
    this.audit('token.issued',reg.id);return {access_token:token,token_type:'Bearer',expires_in:ttl,scope:READ_SCOPE};
  }
  private createRegistration(owner='',name='Anonymous agent'): Registration {
    if(owner)this.ownerCapacity(owner);
    const ownerExpiry=owner?this.ownerExpiry(owner):Infinity;
    const r={id:random('reg_'),owner,name,version:1,expires:Math.min(ownerExpiry,this.now()+(owner?30:1)*86400),revoked:false};
    this.put('registration',r.id,r,r.expires);this.audit('registration.created',r.id);return r;
  }
  private revokeRegistration(reg: Registration): void {reg.revoked=true;reg.version++;this.put('registration',reg.id,reg,reg.expires);this.audit('registration.revoked',reg.id);}
  private ownerExpiry(owner: string): number {
    const row=Array.from(this.sql.exec("SELECT expires FROM auth_records WHERE kind='owner' AND id=? AND expires>?",owner,this.now()))[0];
    if(!row)throw new AuthError('invalid_owner');return Number(row.expires);
  }
  private ownerCapacity(owner: string): void {
    const row=Array.from(this.sql.exec("SELECT COUNT(*) AS total FROM auth_records WHERE kind='registration' AND json_extract(value,'$.owner')=? AND json_extract(value,'$.revoked')=0 AND expires>?",owner,this.now()))[0];
    if(Number(row?.total)>=200)throw new AuthError('account_capacity',429);
  }
  private async session(request: Request): Promise<Session|undefined> {
    const token=request.headers.get('Cookie')?.split(';').map(x=>x.trim()).find(x=>x.startsWith('__Host-mcp_owner='))?.slice(17);
    return token ? this.get<Session>('session',await digest(token)) : undefined;
  }
  private sameOrigin(request: Request): void {if(request.headers.get('Origin')!==this.origin)throw new AuthError('invalid_origin',403);}
  private async owner(request: Request,data: RecordValue): Promise<Session> {
    this.sameOrigin(request);const session=await this.session(request);if(!session||data.csrf!==session.csrf||!this.get('owner',session.owner))throw new AuthError('invalid_session',403);return session;
  }
  private accountForms(session: Session|undefined): string {
    if(!session)return `<p>No email or personal profile is collected. Create an account protected by a random recovery key. Save that key privately; it is the only way to sign in again.</p><form method="post" action="/agent/account"><input type="hidden" name="action" value="create"><button>Create recovery-key account</button></form><section><form method="post" action="/agent/account"><input type="hidden" name="action" value="login"><label>Recovery key<input name="recovery_key" type="password" required autocomplete="current-password" maxlength="100"></label><button>Sign in</button></form></section>`;
    const regs=Array.from(this.sql.exec("SELECT value FROM auth_records WHERE kind='registration' AND json_extract(value,'$.owner')=? AND json_extract(value,'$.revoked')=0 AND expires>? ORDER BY expires DESC LIMIT 200",session.owner,this.now())).map(row=>JSON.parse(String(row.value)) as Registration);
    return `<p>Account ID: <code>${escape(session.owner)}</code></p><p>Give this account ID to your agent when requesting a claim. Keep your recovery key private.</p><p><a href="/agent/claim">Claim an agent</a></p>${regs.map(r=>`<section><p>${escape(r.name)}<br><small>${escape(r.id)}</small></p><form method="post" action="/agent/account"><input type="hidden" name="csrf" value="${session.csrf}"><input type="hidden" name="registration" value="${r.id}"><button name="action" value="revoke">Revoke agent access</button></form></section>`).join('')||'<p>No claimed agents yet.</p>'}<form method="post" action="/agent/account"><input type="hidden" name="csrf" value="${session.csrf}"><button name="action" value="logout">Sign out</button></form>`;
  }
  private async browserAccount(request: Request): Promise<Response> {
    if(request.method==='GET')return page('Agent account',this.accountForms(await this.session(request)));
    if(request.method!=='POST')throw new AuthError('method_not_allowed',405);
    this.sameOrigin(request);const data=await body(request);let account='',recovery='';
    if(data.action==='create') {
      this.limit('owner-create:'+request.headers.get('x-auth-client-key'),5,3600);this.limit('owner-create-global',100,3600);
      account=random('owner_');recovery=random('recover_');this.put('owner',account,{key:await digest(recovery)},this.now()+90*86400);
      this.put('recovery',await digest(recovery),{owner:account},this.now()+90*86400);
    } else if(data.action==='login') {
      this.limit('login:'+request.headers.get('x-auth-client-key'),10,600);
      const stored=this.get<{owner:string}>('recovery',await digest(field(data.recovery_key,100)));
      if(!stored||!this.get('owner',stored.owner))throw new AuthError('invalid_credentials',401);account=stored.owner;
    } else {
      const session=await this.owner(request,data);
      if(data.action==='logout') {
        const cookie=request.headers.get('Cookie')?.split(';').map(x=>x.trim()).find(x=>x.startsWith('__Host-mcp_owner='))?.slice(17);
        if(cookie)this.remove('session',await digest(cookie));return page('Signed out','<p><a href="/agent/account">Sign in again</a></p>',{'Set-Cookie':'__Host-mcp_owner=; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'});
      }
      if(data.action!=='revoke')throw new AuthError('invalid_request');const reg=this.registration(field(data.registration,100));
      if(reg.owner!==session.owner)throw new AuthError('forbidden',403);this.revokeRegistration(reg);return page('Agent access revoked',this.accountForms(session));
    }
    const token=random(),session={owner:account,csrf:random()};this.put('session',await digest(token),session,this.now()+3600);
    const key=recovery?`<section><strong>Save your recovery key now. It is shown once.</strong><p><code>${escape(recovery)}</code></p><p>Anyone with this key can manage this account's agent registrations. The account expires after 90 days.</p></section>`:'';
    return page('Agent account',key+this.accountForms(session),{'Set-Cookie':`__Host-mcp_owner=${token}; Secure; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600`});
  }
  private async claimStart(data: RecordValue): Promise<Response> {
    const claimToken=field(data.claim_token,100),key=await digest(claimToken),old=this.get<Claim>('claim',key);
    if(!old||old.consumed)throw new AuthError('invalid_claim_token');const reg=this.registration(old.registration);
    if(reg.owner)throw new AuthError('claimed_or_in_flight');const owner=field(data.owner_id,100);
    if(!this.get('owner',owner))throw new AuthError('invalid_owner');
    // A fresh high-entropy attempt URL is required as well as the short code.
    const attempt=random('attempt_'),code=userCode();
    const attemptHash=await digest(attempt),codeHash=await digest(code);
    const current=this.get<Claim>('claim',key);if(!current||current.owner)throw new AuthError('claimed_or_in_flight');
    current.owner=owner;current.attempt=attemptHash;current.code=codeHash;current.expires=this.now()+600;current.tries=0;
    this.put('claim',key,current,current.expires);this.put('attempt',current.attempt,{claim:key},current.expires);this.audit('claim.requested',reg.id);
    return json({registration_id:reg.id,claim_token:claimToken,claim:{user_code:code,verification_uri:this.origin+'/agent/claim?attempt='+attempt,expires_in:600,interval:5}});
  }
  private async browserClaim(request: Request): Promise<Response> {
    const url=new URL(request.url);
    if(request.method==='GET') {
      const attempt=url.searchParams.get('attempt')||'',session=await this.session(request);
      if(!session)return page('Sign in to claim an agent','<p><a href="/agent/account">Sign in or create an agent account</a>, then reopen the private claim link your agent supplied. Enter its six-digit code only if you requested this connection.</p>');
      return page('Claim an agent',`<p>Confirm the code supplied by your agent. This grants only public-data read access; it grants no operator access.</p><form method="post" action="/agent/claim"><input type="hidden" name="csrf" value="${session.csrf}"><input type="hidden" name="attempt" value="${escape(attempt)}"><label>Six-digit code<input name="user_code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="off"></label><button>Claim agent</button></form>`);
    }
    if(request.method!=='POST')throw new AuthError('method_not_allowed',405);const data=await body(request),session=await this.owner(request,data);
    const attempt=await digest(field(data.attempt,100)),entry=this.get<{claim:string}>('attempt',attempt);
    if(!entry)throw new AuthError('expired_token');const c=this.get<Claim>('claim',entry.claim);
    if(!c||c.consumed||c.attempt!==attempt||c.owner!==session.owner||c.tries>=5)throw new AuthError('invalid_claim',403);
    c.tries++;this.put('claim',entry.claim,c,c.expires);
    if(c.code!==await digest(field(data.user_code,6)))throw new AuthError('invalid_code',403);
    const reg=this.registration(c.registration);if(reg.owner)throw new AuthError('claimed_or_in_flight');this.ownerCapacity(session.owner);
    reg.owner=session.owner;reg.version++;reg.expires=Math.min(this.ownerExpiry(session.owner),this.now()+30*86400);this.put('registration',reg.id,reg,reg.expires);this.remove('attempt',attempt);this.audit('claim.confirmed',reg.id);
    return page('Agent claimed','<p>Your agent can finish exchanging its claim token. Older pre-claim credentials no longer work.</p><p><a href="/agent/account">Manage agent access</a></p>');
  }
  private validRedirect(value: unknown): string {
    const text=field(value,2048);let url:URL;try{url=new URL(text);}catch{throw new AuthError('invalid_redirect_uri');}
    if(url.hash||url.username||url.password||!(url.protocol==='https:'||(url.protocol==='http:'&&['127.0.0.1','[::1]'].includes(url.hostname))))throw new AuthError('invalid_redirect_uri');return text;
  }
  private authRequest(data: RecordValue): {client: string;redirect: string;challenge: string;state: string;name: string} {
    const client=field(data.client_id,100),stored=this.get<Client>('client',client),redirect=field(data.redirect_uri,2048);
    if(!stored||!stored.redirects.includes(redirect))throw new AuthError('invalid_redirect_uri');
    if(data.response_type!=='code'||data.code_challenge_method!=='S256'||!/^[A-Za-z0-9_-]{43}$/.test(String(data.code_challenge)))throw new AuthError('invalid_request');scope(data.scope);
    return {client,redirect,challenge:String(data.code_challenge),state:typeof data.state==='string'?data.state.slice(0,512):'',name:stored.name};
  }
  private async authorize(request: Request): Promise<Response> {
    const params=new URL(request.url).searchParams;
    if(request.method==='GET'&&[...params.keys()].some(k=>params.getAll(k).length>1))throw new AuthError('invalid_request');
    const data=request.method==='GET'?Object.fromEntries(params):await body(request),auth=this.authRequest(data);
    if(request.method==='GET') {
      const session=await this.session(request);if(!session)return page('Sign in to authorize','<p><a href="/agent/account">Sign in or create an agent account</a>, then reopen the authorization link from your client.</p>');
      const hidden=Object.entries(data).filter(([k])=>['client_id','redirect_uri','response_type','code_challenge_method','code_challenge','state','scope'].includes(k)).map(([k,v])=>`<input type="hidden" name="${k}" value="${escape(String(v))}">`).join('');
      return page('Authorize read-only access',`<p><strong>${escape(auth.name)}</strong> requests <code>${READ_SCOPE}</code>. Data reads retain the existing shared limits. Only continue if you started this request.</p><p>Return address: <code>${escape(auth.redirect)}</code></p><form method="post" action="/oauth2/authorize">${hidden}<input type="hidden" name="csrf" value="${session.csrf}"><button>Allow read-only access</button></form>`);
    }
    const session=await this.owner(request,data),reg=this.createRegistration(session.owner,auth.name),code=random();
    this.put('code',await digest(code),{registration:reg.id,client:auth.client,redirect:auth.redirect,challenge:auth.challenge},this.now()+60);
    const target=new URL(auth.redirect);target.searchParams.set('code',code);if(auth.state)target.searchParams.set('state',auth.state);
    return new Response(null,{status:303,headers:{...commonHeaders,Location:target.href}});
  }
  private async token(data: RecordValue): Promise<Response> {
    if(data.resource!==undefined&&data.resource!==this.origin+'/agent/data')throw new AuthError('invalid_target');scope(data.scope);
    if(data.grant_type===JWT_GRANT) {
      const {reg}=await this.verify(field(data.assertion),'oauth-id-jag+jwt',this.origin);return json(await this.access(reg));
    }
    if(data.grant_type===CLAIM_GRANT) {
      const key=await digest(field(data.claim_token,100)),c=this.get<Claim>('claim',key);if(!c||c.consumed)throw new AuthError('expired_token');
      if(c.poll&&this.now()-c.poll<5)throw new AuthError('slow_down');c.poll=this.now();this.put('claim',key,c,c.expires);
      const reg=this.registration(c.registration);if(!reg.owner)throw new AuthError('authorization_pending');
      c.consumed=true;this.put('claim',key,c,c.expires);return json({...await this.access(reg),...await this.assertion(reg)});
    }
    if(data.grant_type==='authorization_code') {
      const key=await digest(field(data.code,100)),code=this.get<Code>('code',key),verifier=field(data.code_verifier,128);
      if(!/^[A-Za-z0-9._~-]{43,128}$/.test(verifier)||!code||code.client!==data.client_id||code.redirect!==data.redirect_uri||code.challenge!==await digest(verifier))throw new AuthError('invalid_grant');
      // Crypto above can yield. Atomically consume the exact stored code afterwards.
      if(!this.get('code',key))throw new AuthError('invalid_grant');this.remove('code',key);return json(await this.access(this.registration(code.registration)));
    }
    throw new AuthError('unsupported_grant_type');
  }
  async handle(request: Request): Promise<Response> {
    const url=new URL(request.url),path=url.pathname;
    try {
      this.cleanup();
      if(request.method==='OPTIONS')return new Response(null,{status:204,headers:{...commonHeaders,'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET, HEAD, POST, OPTIONS','Access-Control-Allow-Headers':'Authorization, Content-Type'}});
      if(path==='/.well-known/oauth-authorization-server'&&['GET','HEAD'].includes(request.method))return json({issuer:this.origin,authorization_endpoint:this.origin+'/oauth2/authorize',token_endpoint:this.origin+'/oauth2/token',jwks_uri:this.origin+'/oauth2/jwks',registration_endpoint:this.origin+'/oauth2/register',revocation_endpoint:this.origin+'/oauth2/revoke',response_types_supported:['code'],grant_types_supported:[JWT_GRANT,CLAIM_GRANT,'authorization_code'],token_endpoint_auth_methods_supported:['none'],code_challenge_methods_supported:['S256'],scopes_supported:[READ_SCOPE],agent_auth:{skill:this.origin+'/auth.md',register_uri:this.origin+'/agent/identity',identity_endpoint:this.origin+'/agent/identity',claim_uri:this.origin+'/agent/identity/claim',claim_endpoint:this.origin+'/agent/identity/claim',identity_types_supported:['anonymous'],anonymous:{credential_types_supported:['identity_assertion']}}});
      if((path==='/.well-known/oauth-protected-resource'||path==='/.well-known/oauth-protected-resource/agent/data')&&['GET','HEAD'].includes(request.method))return json({resource:this.origin+'/agent/data',resource_name:'mcp.hk optional authenticated public-data reads',authorization_servers:[this.origin],scopes_supported:[READ_SCOPE],bearer_methods_supported:['header'],resource_documentation:this.origin+'/auth.md'});
      if(path==='/oauth2/jwks'&&['GET','HEAD'].includes(request.method))return json({keys:[{...this.jwk,kid:this.kid,alg:'ES256',use:'sig',key_ops:['verify']}]});
      this.limit('request:'+request.headers.get('x-auth-client-key'),60,60);this.limit('requests-global',10000,86400);
      if(path.startsWith('/agent/data')) {
        if(!['GET','HEAD'].includes(request.method))throw new AuthError('method_not_allowed',405);
        if(path!=='/agent/data'&&!protectedDataPath(path))throw new AuthError('not_found',404);
        try {const {reg}=await this.verify(field(request.headers.get('Authorization')?.replace(/^Bearer /,'')),'at+jwt',this.origin+'/agent/data');return json({registration_id:reg.id,scope:READ_SCOPE,interfaces:['/agent/data/packs','/agent/data/catalogue/datasets','/agent/data/status']});}
        catch(error) {if(!(error instanceof AuthError))throw error;return json({error:'invalid_token'},401,{'WWW-Authenticate':`Bearer resource_metadata="${this.origin}/.well-known/oauth-protected-resource", error="invalid_token"`});}
      }
      if(path==='/agent/account')return await this.browserAccount(request);
      if(path==='/agent/claim')return await this.browserClaim(request);
      if(path==='/oauth2/authorize'&&['GET','POST'].includes(request.method))return await this.authorize(request);
      if(request.method!=='POST')throw new AuthError('method_not_allowed',405);
      const data=await body(request);
      if(path==='/agent/identity') {
        if(data.type!=='anonymous')throw new AuthError('unsupported_identity_type');scope(data.scopes??data.scope);
        this.limit('registration:'+request.headers.get('x-auth-client-key'),5,3600);this.limit('registration-global',100,3600);
        const r=this.createRegistration('',typeof data.name==='string'?data.name.slice(0,80):'Anonymous agent'),token=random('clm_'),expiry=this.now()+86400;
        this.put('claim',await digest(token),{registration:r.id,owner:'',attempt:'',code:'',expires:expiry,tries:0,poll:0,consumed:false},expiry);
        return json({registration_id:r.id,registration_type:'anonymous',...await this.assertion(r),pre_claim_scopes:[READ_SCOPE],claim_url:this.origin+'/agent/identity/claim',claim_token:token,claim_token_expires:new Date(expiry*1000).toISOString(),post_claim_scopes:[READ_SCOPE]},201);
      }
      if(path==='/agent/identity/claim')return await this.claimStart(data);
      if(path==='/oauth2/token')return await this.token(data);
      if(path==='/oauth2/register') {
        this.limit('client-registration:'+request.headers.get('x-auth-client-key'),5,3600);this.limit('client-registration-global',100,3600);
        if(!Array.isArray(data.redirect_uris)||!data.redirect_uris.length||data.redirect_uris.length>5||!['none',undefined].includes(data.token_endpoint_auth_method as string|undefined))throw new AuthError('invalid_client_metadata');
        const id=random('client_'),redirects=data.redirect_uris.map(x=>this.validRedirect(x)),name=typeof data.client_name==='string'?data.client_name.slice(0,80):'Public data client';
        this.put('client',id,{redirects,name},this.now()+30*86400);return json({client_id:id,client_id_issued_at:this.now(),client_name:name,redirect_uris:redirects,token_endpoint_auth_method:'none',grant_types:['authorization_code'],response_types:['code']},201);
      }
      if(path==='/oauth2/revoke') {
        const token=field(data.token);for(const [typ,aud] of [['at+jwt',this.origin+'/agent/data'],['oauth-id-jag+jwt',this.origin]]) {
          try{const {reg,jti}=await this.verify(token,typ,aud);if(typ==='at+jwt'){this.remove(typ,jti);this.audit('token.revoked',reg.id);}else this.revokeRegistration(reg);break;}catch(error){if(!(error instanceof AuthError))throw error;/* RFC 7009: unknown/expired tokens still return 200. */}
        }return json({});
      }
      throw new AuthError('not_found',404);
    } catch(error) {
      if(error instanceof AuthError)return json({error:error.code},error.status,error.status===429?{'Retry-After':'60'}:{});
      if(error instanceof SyntaxError||error instanceof TypeError)return json({error:'invalid_request'},400);
      return json({error:'temporarily_unavailable'},503);
    }
  }
}
