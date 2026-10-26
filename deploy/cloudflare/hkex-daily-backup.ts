/** A separate, prefix-only capability for the ordinary host summary updater. */
export const HKEX_PREFIX='curated/hkex-daily/daily/';
export const MAX_HKEX_DUMP=64*1024*1024;
type BackupEnv={BACKUPS:R2Bucket;OPS_TOKEN?:string;HKEX_DAILY_BACKUP_TOKEN?:string;OFFICIAL_BACKUP_TOKEN?:string;CURATED_BACKEND_TOKEN?:string};
const denied=()=>new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
const stamp=/^\d{8}T\d{6}Z-[a-f0-9]{8}$/;
const names=new Set(['summary.dump','manifest.json']);
const digest=/^[a-f0-9]{64}$/;
export async function hkexDailyBackup(request:Request,env:BackupEnv,admit:(bytes:number,write:boolean)=>Promise<boolean>=async()=>false):Promise<Response>{
 const u=new URL(request.url),token=env.HKEX_DAILY_BACKUP_TOKEN;
 if(u.origin!=='https://mcp.hk'||u.search||!token||token.length<32||[env.OPS_TOKEN,env.OFFICIAL_BACKUP_TOKEN,env.CURATED_BACKEND_TOKEN].includes(token))return denied();
 const hash=async(s:string)=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));
 const a=await hash(request.headers.get('authorization')||''),b=await hash('Bearer '+token);let difference=0;for(let i=0;i<32;i++)difference|=a[i]^b[i];if(difference)return denied();
 const tail=u.pathname.slice('/__hkex-daily-backup/'.length),parts=tail.split('/');
 const latest=tail==='latest.json',key=latest?'curated/hkex-daily/latest.json':HKEX_PREFIX+tail;
 if(!latest&&(parts.length!==2||!stamp.test(parts[0])||!names.has(parts[1])))return denied();
 const allowed=async(n:number,w:boolean)=>{try{return await admit(n,w);}catch{return false;}};
 if(['GET','HEAD'].includes(request.method)){
  if(!await allowed(0,false))return new Response('Backup budget unavailable',{status:429});
  const h=await env.BACKUPS.head(key);if(!h)return denied();
  if(request.method==='GET'&&!await allowed(h.size,false))return new Response('Backup budget unavailable',{status:429});
  const o=request.method==='HEAD'?h:await env.BACKUPS.get(key);if(!o)return denied();
  return new Response(request.method==='HEAD'?null:(o as R2ObjectBody).body,{headers:{'Content-Type':latest||parts[1]==='manifest.json'?'application/json':'application/octet-stream','Content-Length':String(o.size),'Cache-Control':'no-store','x-object-sha256':o.customMetadata?.sha256||''}});
 }
 if(latest||request.method!=='PUT')return denied();
 const n=Number(request.headers.get('content-length')),sha=request.headers.get('x-object-sha256')||'';
 if(!Number.isSafeInteger(n)||n<=0||n>(parts[1]==='summary.dump'?MAX_HKEX_DUMP:1024*1024)||!digest.test(sha)||!request.body)return new Response('Invalid backup metadata',{status:400});
 if(!await allowed(n,true))return new Response('Backup budget unavailable',{status:429});
 let body:ReadableStream|Uint8Array=request.body,manifest:any=null;
 if(parts[1]==='manifest.json'){
  try{
   const reader=request.body.getReader(),chunks:Uint8Array[]=[];let length=0;
   for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>n){await reader.cancel();throw Error();}chunks.push(value);}
   if(length!==n)throw Error();const bytes=new Uint8Array(length);let at=0;for(const c of chunks){bytes.set(c,at);at+=c.length;}
   if(Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('')!==sha)throw Error();
   manifest=JSON.parse(new TextDecoder().decode(bytes));
   const h=await env.BACKUPS.head(HKEX_PREFIX+parts[0]+'/summary.dump');
   if(manifest.source!=='hkex_daily_summary'||manifest.stamp!==parts[0]||!['candidate','accepted'].includes(manifest.stage)||!h||h.size!==manifest.dump?.bytes||h.customMetadata?.sha256!==manifest.dump?.sha256||!digest.test(manifest.dump?.sha256||''))throw Error();
   if(manifest.stage==='accepted'){
    if(manifest.restoreVerified!==true||!Number.isSafeInteger(manifest.publicationRevision)||manifest.publicationRevision<1||!/^hkex-daily-[a-f0-9]{32}$/.test(manifest.version||'')||Object.keys(manifest.allTables||{}).sort().join(',')!=='control,records,reports,requests,runs,version_reports,versions')throw Error();
    for(const r of Object.values(manifest.allTables) as any[])if(!Number.isSafeInteger(r.rows)||r.rows<0||!digest.test(r.sha256||''))throw Error();
   }
   body=bytes;
  }catch{return new Response('Restore manifest invalid or dump unverified',{status:409});}
 }
 try{
  let saved=await env.BACKUPS.put(key,body,{sha256:sha,onlyIf:{etagDoesNotMatch:'*'},customMetadata:{sha256:sha}});if(!saved){const existing=await env.BACKUPS.head(key);if(!manifest||existing?.size!==n||existing.customMetadata?.sha256!==sha)return new Response('Immutable object exists',{status:409});saved=existing;}
  if(manifest?.stage==='accepted'){
   const latestKey='curated/hkex-daily/latest.json',old=await env.BACKUPS.get(latestKey),previous=old?await old.json<any>():null;
   if(previous&&(previous.publicationRevision>manifest.publicationRevision||previous.publicationRevision===manifest.publicationRevision&&(previous.version!==manifest.version||previous.stamp>manifest.stamp)))return new Response('Recovery pointer conflict',{status:409});
   const value=JSON.stringify({source:manifest.source,stamp:parts[0],version:manifest.version,publicationRevision:manifest.publicationRevision,dump:manifest.dump,manifestSha256:sha});
   const advanced=await env.BACKUPS.put(latestKey,value,{onlyIf:old?{etagMatches:old.etag}:{etagDoesNotMatch:'*'}});if(!advanced)return new Response('Recovery pointer conflict',{status:409});
  }
  return Response.json({stored:true,bytes:saved.size,sha256:sha,recoveryAdvanced:manifest?.stage==='accepted'},{headers:{'Cache-Control':'no-store'}});
 }catch{return new Response('Backup upload not confirmed',{status:503});}
}

export function hkexDailyBackupAdmission(sql:SqlStorage,bytes:number,write:boolean,now=Date.now()):boolean{
 if(!Number.isSafeInteger(bytes)||bytes<0||bytes>MAX_HKEX_DUMP)return false;
 sql.exec('CREATE TABLE IF NOT EXISTS hkex_daily_backup_budget(day INTEGER PRIMARY KEY,writes INTEGER,reads INTEGER,upload_bytes INTEGER,read_bytes INTEGER)');const day=Math.floor(now/86400000);
 sql.exec('DELETE FROM hkex_daily_backup_budget WHERE day<?',day-30);
 const r=[...sql.exec<{writes:number;reads:number;upload_bytes:number;read_bytes:number}>('SELECT writes,reads,upload_bytes,read_bytes FROM hkex_daily_backup_budget WHERE day=?',day)][0]||{writes:0,reads:0,upload_bytes:0,read_bytes:0};
 if(write?(r.writes>=64||r.upload_bytes+bytes>256*1024*1024):(r.reads>=128||r.read_bytes+bytes>512*1024*1024))return false;
 sql.exec('INSERT OR REPLACE INTO hkex_daily_backup_budget VALUES(?,?,?,?,?)',day,r.writes+(write?1:0),r.reads+(write?0:1),r.upload_bytes+(write?bytes:0),r.read_bytes+(write?0:bytes));return true;
}
