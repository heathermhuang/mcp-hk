// Dedicated, optional host capability. It never authorizes gateway operations.
export const OFFICIAL_PREFIX='curated/official/daily/';
export const MAX_OFFICIAL_DUMP=256*1024*1024;
type BackupEnv={BACKUPS:R2Bucket;OFFICIAL_BACKUP_TOKEN?:string;OPS_TOKEN?:string};
const stamp=/^\d{8}T\d{6}Z-[a-f0-9]{8}$/;
const names=new Set(['official.dump','manifest.json','source.json']);
const denied=()=>new Response('Not found',{status:404,headers:{'Cache-Control':'no-store'}});
export async function officialBackup(request:Request,env:BackupEnv):Promise<Response>{
 const url=new URL(request.url),token=env.OFFICIAL_BACKUP_TOKEN;
 if(!token||token===env.OPS_TOKEN||token.length<32||url.origin!=='https://mcp.hk'||url.search)return denied();
 const hash=async(value:string)=>new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)));
 const a=await hash(request.headers.get('authorization')||''),b=await hash('Bearer '+token);
 let mismatch=0;for(let i=0;i<a.length;i++)mismatch|=a[i]^b[i];if(mismatch)return denied();
 const tail=url.pathname.slice('/__company-backup/'.length),parts=tail.split('/');
 if(parts.length!==2||!stamp.test(parts[0])||!names.has(parts[1]))return denied();
 const key=OFFICIAL_PREFIX+tail;
 if(request.method==='GET'||request.method==='HEAD'){
  const object=request.method==='HEAD'?await env.BACKUPS.head(key):await env.BACKUPS.get(key);
  if(!object)return denied();
  return new Response(request.method==='HEAD'?null:(object as R2ObjectBody).body,{headers:{'Content-Type':'application/octet-stream','Content-Length':String(object.size),'Cache-Control':'no-store','x-object-sha256':object.customMetadata?.sha256||''}});
 }
 if(request.method!=='PUT')return denied();
 const length=Number(request.headers.get('content-length')),sha=request.headers.get('x-object-sha256')||'';
 const max=parts[1]==='official.dump'?MAX_OFFICIAL_DUMP:1024*1024;
 if(!Number.isSafeInteger(length)||length<=0||length>max||!/^[a-f0-9]{64}$/.test(sha)||!request.body)return new Response('Invalid backup metadata',{status:400});
 // Provider verifies SHA-256 while streaming; conditional put cannot replace a copy.
 try{
  const saved=await env.BACKUPS.put(key,request.body,{sha256:sha,onlyIf:{etagDoesNotMatch:'*'},customMetadata:{sha256:sha}});
  if(!saved)return new Response('Immutable object already exists',{status:409});
  return Response.json({stored:true,bytes:saved.size,sha256:sha},{headers:{'Cache-Control':'no-store'}});
 }catch{return new Response('Backup upload failed',{status:503,headers:{'Cache-Control':'no-store'}});}
}
