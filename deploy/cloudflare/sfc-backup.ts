/** Optional source-only SFC recovery capability. Unconfigured means closed. */
export const SFC_PREFIX='curated/sfc/source/';
export const MAX_SFC_DUMP=64*1024*1024;
type Env={BACKUPS:R2Bucket;SFC_BACKUP_TOKEN?:string;SFC_BACKUP_POLICY_SHA256?:string;SFC_BACKUP_RETENTION_SECONDS?:string;OPS_TOKEN?:string;OFFICIAL_BACKUP_TOKEN?:string;HKEX_DAILY_BACKUP_TOKEN?:string;CURATED_BACKEND_TOKEN?:string};
const digest=/^[a-f0-9]{64}$/,stamp=/^\d{8}T\d{6}Z-[a-f0-9]{8}$/;
const tables='attempts,budgets,captures,corporations,holds,migrations,pointer,policies,runs,versions';
const denied=()=>new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
export async function sfcBackup(request:Request,env:Env,admit:(n:number,write:boolean)=>Promise<boolean>=async()=>false):Promise<Response>{
 const u=new URL(request.url),token=env.SFC_BACKUP_TOKEN,retention=Number(env.SFC_BACKUP_RETENTION_SECONDS);
 if(u.origin!=='https://mcp.hk'||u.search||!token||token.length<32||[env.OPS_TOKEN,env.OFFICIAL_BACKUP_TOKEN,env.HKEX_DAILY_BACKUP_TOKEN,env.CURATED_BACKEND_TOKEN].includes(token)||!digest.test(env.SFC_BACKUP_POLICY_SHA256||'')||!Number.isSafeInteger(retention)||retention<1)return denied();
 const hash=async(s:string)=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));
 const a=await hash(request.headers.get('authorization')||''),b=await hash('Bearer '+token);let difference=0;for(let n=0;n<32;n++)difference|=a[n]^b[n];if(difference)return denied();
 const tail=u.pathname.slice('/__sfc-backup/'.length),parts=tail.split('/'),latest=tail==='latest.json';
 const allowed=async(n:number,w:boolean)=>{try{return await admit(n,w);}catch{return false;}};
 if(tail==='capability'&&request.method==='GET')return await allowed(0,false)?Response.json({source:'sfc_register',maxDumpBytes:MAX_SFC_DUMP,policySha256:env.SFC_BACKUP_POLICY_SHA256,configuredRetentionSeconds:retention,publicModesGranted:false},{headers:{'Cache-Control':'no-store'}}):new Response('Budget unavailable',{status:429});
 if(!latest&&(parts.length!==2||!stamp.test(parts[0])||!['source.dump','manifest.json'].includes(parts[1])))return denied();
 const key=latest?'curated/sfc/latest.json':SFC_PREFIX+tail;
 if(['GET','HEAD'].includes(request.method)){
  if(!await allowed(0,false))return new Response('Budget unavailable',{status:429});
  const h=await env.BACKUPS.head(key);if(!h||Number(h.customMetadata?.expiresAt||0)<=Date.now())return denied();
  if(request.method==='GET'&&!await allowed(h.size,false))return new Response('Budget unavailable',{status:429});
  const object=request.method==='HEAD'?h:await env.BACKUPS.get(key);if(!object)return denied();
  return new Response(request.method==='HEAD'?null:(object as R2ObjectBody).body,{headers:{'Content-Type':latest||parts[1]==='manifest.json'?'application/json':'application/octet-stream','Content-Length':String(object.size),'x-object-sha256':object.customMetadata?.sha256||'','Cache-Control':'no-store'}});
 }
 if(latest||request.method!=='PUT')return denied();
 const length=Number(request.headers.get('content-length')),sha=request.headers.get('x-object-sha256')||'',expiresAt=Number(request.headers.get('x-source-expires-at'));
 if(!Number.isSafeInteger(length)||length<1||length>(parts[1]==='source.dump'?MAX_SFC_DUMP:1024*1024)||!digest.test(sha)||!request.body||!Number.isSafeInteger(expiresAt)||expiresAt<=Date.now()||expiresAt>Date.now()+retention*1000)return new Response('Invalid recovery metadata',{status:400});
 if(!await allowed(length,true))return new Response('Budget unavailable',{status:429});
 let body:ReadableStream|Uint8Array,manifest:any=null;
 const reader=request.body.getReader();let received=0;
 const bounded=new ReadableStream<Uint8Array>({async pull(controller){try{const item=await reader.read();if(item.done){if(received!==length)throw Error();controller.close();return;}received+=item.value.length;if(received>length)throw Error();controller.enqueue(item.value);}catch(error){await reader.cancel();controller.error(error);}},async cancel(){await reader.cancel();}});
 if(parts[1]==='manifest.json'){
  try{
   const bytes=new Uint8Array(await new Response(bounded).arrayBuffer());
   if(Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('')!==sha)throw Error();
   manifest=JSON.parse(new TextDecoder().decode(bytes));const dump=await env.BACKUPS.head(SFC_PREFIX+parts[0]+'/source.dump');
   if(manifest.source!=='sfc_register'||manifest.stamp!==parts[0]||!['candidate','accepted'].includes(manifest.stage)||manifest.policySha256!==env.SFC_BACKUP_POLICY_SHA256||!/^sfc-[a-f0-9]{32}$/.test(manifest.version||'')||!dump||dump.size!==manifest.dump?.bytes||dump.customMetadata?.sha256!==manifest.dump?.sha256||Number(dump.customMetadata?.expiresAt)!==expiresAt||manifest.expiresAt!==expiresAt)throw Error();
   if(manifest.stage==='accepted'){
    if(manifest.restoreVerified!==true||manifest.acceptedPointerIncluded!==true||Object.keys(manifest.allTables||{}).sort().join(',')!==tables||manifest.previousManifestSha256!==null&&!digest.test(manifest.previousManifestSha256||''))throw Error();
    for(const row of Object.values(manifest.allTables) as any[])if(!Number.isSafeInteger(row.rows)||row.rows<0||!digest.test(row.sha256||''))throw Error();
   }
   body=bytes;
  }catch{return new Response('Unverified recovery manifest',{status:409});}
 }else body=bounded;
 try{
  const metadata={sha256:sha,expiresAt:String(expiresAt)};
  let saved=await env.BACKUPS.put(key,body,{sha256:sha,onlyIf:{etagDoesNotMatch:'*'},customMetadata:metadata});
  if(!saved){const prior=await env.BACKUPS.head(key);if(!manifest||prior?.size!==length||prior.customMetadata?.sha256!==sha)return new Response('Immutable object exists',{status:409});saved=prior;}
  if(saved.size!==length)throw Error();
  if(manifest?.stage==='accepted'){
   const latestKey='curated/sfc/latest.json',old=await env.BACKUPS.get(latestKey),previous=old&&Number(old.customMetadata?.expiresAt||0)>Date.now()?await old.json<any>():null;
   if(previous?.manifestSha256===sha&&previous?.stamp===parts[0])return Response.json({stored:true,bytes:saved.size,sha256:sha,recoveryAdvanced:true},{headers:{'Cache-Control':'no-store'}});
   if((previous?.manifestSha256??null)!==manifest.previousManifestSha256)return new Response('Recovery predecessor changed',{status:409});
   const value=JSON.stringify({source:'sfc_register',version:manifest.version,stamp:parts[0],dump:manifest.dump,manifestSha256:sha,expiresAt});
   const advanced=await env.BACKUPS.put(latestKey,value,{onlyIf:old?{etagMatches:old.etag}:{etagDoesNotMatch:'*'},customMetadata:{expiresAt:String(expiresAt)}});if(!advanced)return new Response('Recovery predecessor changed',{status:409});
  }
  return Response.json({stored:true,bytes:saved.size,sha256:sha,recoveryAdvanced:manifest?.stage==='accepted'},{headers:{'Cache-Control':'no-store'}});
 }catch{return new Response('Recovery upload unconfirmed',{status:503});}
}

export function sfcBackupAdmission(sql:SqlStorage,bytes:number,write:boolean,now=Date.now()):boolean{
 if(!Number.isSafeInteger(bytes)||bytes<0||bytes>MAX_SFC_DUMP)return false;
 sql.exec('CREATE TABLE IF NOT EXISTS sfc_backup_budget(day INTEGER PRIMARY KEY,writes INTEGER,reads INTEGER,upload_bytes INTEGER,read_bytes INTEGER)');
 const day=Math.floor(now/86400000),r=[...sql.exec<{writes:number;reads:number;upload_bytes:number;read_bytes:number}>('SELECT writes,reads,upload_bytes,read_bytes FROM sfc_backup_budget WHERE day=?',day)][0]||{writes:0,reads:0,upload_bytes:0,read_bytes:0};
 if(write?(r.writes>=64||r.upload_bytes+bytes>256*1024*1024):(r.reads>=128||r.read_bytes+bytes>512*1024*1024))return false;
 sql.exec('INSERT OR REPLACE INTO sfc_backup_budget VALUES(?,?,?,?,?)',day,r.writes+(write?1:0),r.reads+(write?0:1),r.upload_bytes+(write?bytes:0),r.read_bytes+(write?0:bytes));return true;
}
