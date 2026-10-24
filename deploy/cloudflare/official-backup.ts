// Dedicated, optional host capability. It never authorizes gateway operations.
export const OFFICIAL_PREFIX='curated/official/daily/';
export const MAX_OFFICIAL_DUMP=256*1024*1024;
type BackupEnv={BACKUPS:R2Bucket;OFFICIAL_BACKUP_TOKEN?:string;OPS_TOKEN?:string};
const stamp=/^\d{8}T\d{6}Z-[a-f0-9]{8}$/;
const names=new Set(['official.dump','manifest.json','source.json']);
const denied=()=>new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
export async function officialBackup(request:Request,env:BackupEnv,admit:(bytes:number,write:boolean)=>Promise<boolean>=async()=>false):Promise<Response>{
 const url=new URL(request.url),token=env.OFFICIAL_BACKUP_TOKEN;
 if(!token||token===env.OPS_TOKEN||token.length<32||url.origin!=='https://mcp.hk'||url.search)return denied();
 const hash=async(value:string)=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));
 const a=await hash(request.headers.get('authorization')||''),b=await hash('Bearer '+token);
 let mismatch=0;for(let i=0;i<a.length;i++)mismatch|=a[i]^b[i];if(mismatch)return denied();
 const tail=url.pathname.slice('/__company-backup/'.length),parts=tail.split('/');
 if(parts.length!==2||!stamp.test(parts[0])||!names.has(parts[1]))return denied();
 const key=OFFICIAL_PREFIX+tail;
 const allowed=async(bytes:number,write:boolean)=>{try{return await admit(bytes,write);}catch{return false;}};
 if(request.method==='GET'||request.method==='HEAD'){
  if(!(await allowed(0,false)))return new Response('Backup budget unavailable',{status:429});
  const head=await env.BACKUPS.head(key);
  if(!head)return denied();
  if(request.method==='GET'&&!(await allowed(head.size,false)))return new Response('Backup budget unavailable',{status:429});
  const object=request.method==='HEAD'?head:await env.BACKUPS.get(key);
  if(!object)return denied();
  return new Response(request.method==='HEAD'?null:(object as R2ObjectBody).body,{headers:{'Content-Type':'application/octet-stream','Content-Length':String(object.size),'Cache-Control':'no-store','x-object-sha256':object.customMetadata?.sha256||''}});
 }
 if(request.method!=='PUT')return denied();
 const length=Number(request.headers.get('content-length')),sha=request.headers.get('x-object-sha256')||'';
 const max=parts[1]==='official.dump'?MAX_OFFICIAL_DUMP:1024*1024;
 if(!Number.isSafeInteger(length)||length<=0||length>max||!/^[a-f0-9]{64}$/.test(sha)||!request.body)return new Response('Invalid backup metadata',{status:400});
 if(!(await allowed(length,true)))return new Response('Backup budget unavailable',{status:429});
 let body:ReadableStream|Uint8Array=request.body;
 if(parts[1]==='manifest.json'){
  try{
   const reader=request.body.getReader(),chunks:Uint8Array[]=[];let size=0;
   for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>length||size>1024*1024){await reader.cancel();return new Response('Invalid manifest',{status:400});}chunks.push(value);}
   if(size!==length)return new Response('Invalid manifest',{status:400});
   const bytes=new Uint8Array(size);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
   const manifest=JSON.parse(new TextDecoder().decode(bytes));
   if(manifest.prefix!==OFFICIAL_PREFIX+parts[0]||Object.keys(manifest.artifacts||{}).sort().join(',')!=='official.dump,source.json')return new Response('Invalid manifest',{status:400});
   for(const name of ['official.dump','source.json']){
    const expected=manifest.artifacts[name],object=await env.BACKUPS.head(OFFICIAL_PREFIX+parts[0]+'/'+name);
    if(!object||object.size!==expected.bytes||object.customMetadata?.sha256!==expected.sha256)return new Response('Manifest dependencies unverified',{status:409});
   }
   body=bytes;
  }catch{return new Response('Invalid manifest',{status:400});}
 }
 // Provider verifies SHA-256 while streaming; conditional put cannot replace a copy.
 try{
  const saved=await env.BACKUPS.put(key,body,{sha256:sha,onlyIf:{etagDoesNotMatch:'*'},customMetadata:{sha256:sha}});
  if(!saved)return new Response('Immutable object already exists',{status:409});
  return Response.json({stored:true,bytes:saved.size,sha256:sha},{headers:{'Cache-Control':'no-store'}});
 }catch{return new Response('Backup upload failed',{status:503,headers:{'Cache-Control':'no-store'}});}
}


export function officialBackupAdmission(sql:SqlStorage,bytes:number,write:boolean,now=Date.now()):boolean {
 if(!Number.isSafeInteger(bytes)||bytes<0||bytes>MAX_OFFICIAL_DUMP)return false;
 sql.exec('CREATE TABLE IF NOT EXISTS official_backup_budget(day INTEGER PRIMARY KEY,writes INTEGER,reads INTEGER,upload_bytes INTEGER,read_bytes INTEGER)');
 const day=Math.floor(now/86400000);
 sql.exec('DELETE FROM official_backup_budget WHERE day < ?',day-30);
 const row=[...sql.exec<{writes:number;reads:number;upload_bytes:number;read_bytes:number}>('SELECT writes,reads,upload_bytes,read_bytes FROM official_backup_budget WHERE day=?',day)][0]||{writes:0,reads:0,upload_bytes:0,read_bytes:0};
 if(write?(row.writes>=16||row.upload_bytes+bytes>1073741824+8388608):(row.reads>=64||row.read_bytes+bytes>2147483648))return false;
 sql.exec('INSERT OR REPLACE INTO official_backup_budget VALUES(?,?,?,?,?)',day,row.writes+(write?1:0),row.reads+(write?0:1),row.upload_bytes+(write?bytes:0),row.read_bytes+(write?0:bytes));
 return true;
}
