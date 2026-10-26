// Dedicated, optional host capability. It never authorizes gateway operations.
export const OFFICIAL_PREFIX='curated/official/daily/';
export const MAX_OFFICIAL_DUMP=256*1024*1024;
export const MAX_OFFICIAL_PART=64*1024*1024;
type BackupEnv={BACKUPS:R2Bucket;OFFICIAL_BACKUP_TOKEN?:string;OPS_TOKEN?:string};
const stamp=/^\d{8}T\d{6}Z-[a-f0-9]{8}$/;
const names=new Set(['official.dump','manifest.json','source.json','official.part-000','official.part-001','official.part-002','official.part-003']);
type Artifact={bytes:number;sha256:string;parts?:Array<{name:string;bytes:number;sha256:string}>};
function validArtifact(value:Artifact,max:number):boolean{return value&&Number.isSafeInteger(value.bytes)&&value.bytes>0&&value.bytes<=max&&/^[a-f0-9]{64}$/.test(value.sha256);}
async function verifiedParts(bucket:R2Bucket,prefix:string,expected:Artifact):Promise<NonNullable<Artifact['parts']>>{
 const parts=expected.parts;
 if(!validArtifact(expected,MAX_OFFICIAL_DUMP)||!Array.isArray(parts)||parts.length<1||parts.length>4)throw new Error('parts');
 let total=0;
 for(let i=0;i<parts.length;i++){
  const p=parts[i];if(p.name!==`official.part-${String(i).padStart(3,'0')}`||!validArtifact(p,MAX_OFFICIAL_PART))throw new Error('part');
  total+=p.bytes;const head=await bucket.head(prefix+'/'+p.name);
  if(!head||head.size!==p.bytes||head.customMetadata?.sha256!==p.sha256)throw new Error('dependency');
 }
 if(total!==expected.bytes)throw new Error('total');return parts;
}
async function* partBytes(bucket:R2Bucket,prefix:string,parts:NonNullable<Artifact['parts']>){
 for(const part of parts){const object=await bucket.get(prefix+'/'+part.name);if(!object||object.size!==part.bytes||object.customMetadata?.sha256!==part.sha256)throw new Error('dependency');
  const reader=object.body.getReader();let total=0;try{for(;;){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>part.bytes)throw new Error('size');yield value;}if(total!==part.bytes)throw new Error('size');}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
 }
}
async function verifyDigest(bucket:R2Bucket,prefix:string,expected:Artifact,parts:NonNullable<Artifact['parts']>){
 const digest=new crypto.DigestStream('SHA-256'),writer=digest.getWriter();
 try{for await(const chunk of partBytes(bucket,prefix,parts))await writer.write(chunk);await writer.close();
  const sha=Array.from(new Uint8Array(await digest.digest),b=>b.toString(16).padStart(2,'0')).join('');if(sha!==expected.sha256)throw new Error('digest');
 }catch(error){await writer.abort(error).catch(()=>{});digest.digest.catch(()=>{});throw error;}
}
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
  if(!head&&parts[1]==='official.dump'){
   try{
    const prefix=OFFICIAL_PREFIX+parts[0],manifest=await env.BACKUPS.get(prefix+'/manifest.json');if(!manifest||manifest.size>1024*1024)return denied();
    const value=await new Response(manifest.body).json() as {prefix:string;artifacts:Record<string,Artifact>};if(value.prefix!==prefix)return denied();
    const expected=value.artifacts['official.dump'],segments=await verifiedParts(env.BACKUPS,prefix,expected);
    if(request.method==='GET'&&!(await allowed(expected.bytes,false)))return new Response('Backup budget unavailable',{status:429});
    const iterator=partBytes(env.BACKUPS,prefix,segments);
    const body=request.method==='HEAD'?null:new ReadableStream({async pull(controller){try{const value=await iterator.next();if(value.done)controller.close();else controller.enqueue(value.value);}catch(error){controller.error(error);}},async cancel(){await iterator.return(undefined);}});
    return new Response(body,{headers:{'Content-Type':'application/octet-stream','Content-Length':String(expected.bytes),'Cache-Control':'no-store','x-object-sha256':expected.sha256}});
   }catch{return denied();}
  }
  if(!head)return denied();
  if(request.method==='GET'&&!(await allowed(head.size,false)))return new Response('Backup budget unavailable',{status:429});
  const object=request.method==='HEAD'?head:await env.BACKUPS.get(key);
  if(!object)return denied();
  return new Response(request.method==='HEAD'?null:(object as R2ObjectBody).body,{headers:{'Content-Type':'application/octet-stream','Content-Length':String(object.size),'Cache-Control':'no-store','x-object-sha256':object.customMetadata?.sha256||''}});
 }
 if(request.method!=='PUT')return denied();
 const length=Number(request.headers.get('content-length')),sha=request.headers.get('x-object-sha256')||'';
 const max=parts[1]==='official.dump'?MAX_OFFICIAL_DUMP:parts[1].startsWith('official.part-')?MAX_OFFICIAL_PART:1024*1024;
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
    const expected=manifest.artifacts[name] as Artifact;
    if(!validArtifact(expected,name==='official.dump'?MAX_OFFICIAL_DUMP:1024*1024))return new Response('Invalid manifest',{status:400});
    if(name==='official.dump'&&expected.parts!==undefined){
     try{const prefix=OFFICIAL_PREFIX+parts[0];if(await env.BACKUPS.head(prefix+'/official.dump'))throw new Error('mixed');const segments=await verifiedParts(env.BACKUPS,prefix,expected);if(!(await allowed(expected.bytes,false)))return new Response('Backup budget unavailable',{status:429});await verifyDigest(env.BACKUPS,prefix,expected,segments);}catch{return new Response('Manifest dependencies unverified',{status:409});}continue;
    }
    if(name==='source.json'&&expected.parts!==undefined)return new Response('Invalid manifest',{status:400});
    const object=await env.BACKUPS.head(OFFICIAL_PREFIX+parts[0]+'/'+name);
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
