import test from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {sfcBackup,sfcBackupAdmission,SFC_PREFIX,MAX_SFC_DUMP} from './sfc-backup.ts';
const token='s'.repeat(48),stamp='20261027T001000Z-aabbccdd',policy='a'.repeat(64),expires=Date.now()+3600000;
const hash=async bytes=>Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex');
function bucket(){const objects=new Map();let revision=0;return {objects,async head(k){return objects.get(k)||null;},async get(k){const o=objects.get(k);return o?{...o,body:new Blob([o.bytes]).stream(),async json(){return JSON.parse(new TextDecoder().decode(o.bytes));}}:null;},async put(k,body,options={}){const old=objects.get(k);if(options.onlyIf?.etagDoesNotMatch==='*'&&old||options.onlyIf?.etagMatches&&options.onlyIf.etagMatches!==old?.etag)return null;const bytes=typeof body==='string'?new TextEncoder().encode(body):body instanceof Uint8Array?body:new Uint8Array(await new Response(body).arrayBuffer());if(options.sha256&&await hash(bytes)!==options.sha256)throw Error('checksum');const row={bytes,size:bytes.length,etag:String(++revision),customMetadata:options.customMetadata||{}};objects.set(k,row);return row;}};}
function env(){return {BACKUPS:bucket(),SFC_BACKUP_TOKEN:token,SFC_BACKUP_POLICY_SHA256:policy,SFC_BACKUP_RETENTION_SECONDS:'86400'};}
function request(tail=stamp+'/source.dump',method='GET',body=null,sha=null,extra={}){return new Request('https://mcp.hk/__sfc-backup/'+tail,{method,headers:{authorization:'Bearer '+token,...(body!==null?{'content-length':String(new TextEncoder().encode(body).length),'x-object-sha256':sha,'x-source-expires-at':String(expires)}:{}),...extra},...(body!==null?{body}:{})});}
const call=(r,e)=>sfcBackup(r,e,async()=>true);
async function uploaded(){const e=env(),sha=await hash(new TextEncoder().encode('abc'));assert.equal((await call(request(undefined,'PUT','abc',sha),e)).status,200);return {e,sha};}
function manifest(sha,stage='accepted'){return {source:'sfc_register',policySha256:policy,stage,stamp,version:'sfc-'+'b'.repeat(32),expiresAt:expires,dump:{bytes:3,sha256:sha},restoreVerified:true,acceptedPointerIncluded:true,previousManifestSha256:null,allTables:Object.fromEntries('attempts,budgets,captures,corporations,holds,migrations,pointer,policies,runs,versions'.split(',').map(k=>[k,{rows:1,sha256:'c'.repeat(64)}]))};}
async function putManifest(e,value){const body=JSON.stringify(value);return call(request(stamp+'/manifest.json','PUT',body,await hash(new TextEncoder().encode(body))),e);}
test('SFC backup is absent until distinct token, policy and retention are configured',async()=>{
 for(const e of [env(),{...env(),SFC_BACKUP_TOKEN:undefined},{...env(),SFC_BACKUP_POLICY_SHA256:undefined},{...env(),SFC_BACKUP_RETENTION_SECONDS:'0'},{...env(),OPS_TOKEN:token}]){
  const r=await call(request('capability'),e);assert.equal(r.status,e.SFC_BACKUP_TOKEN&&e.SFC_BACKUP_POLICY_SHA256&&e.SFC_BACKUP_RETENTION_SECONDS==='86400'&&e.OPS_TOKEN!==token?200:404);
 }
 const capability=await (await call(request('capability'),env())).json();assert.equal(capability.publicModesGranted,false);
});
test('origin, names, methods and actual stream lengths cannot escape source scope or budget',async()=>{
 const e=env();for(const name of ['../latest.snapshot.tar.gz','arbitrary.dump',stamp+'/source.dump/extra',stamp+'/source.dump?q=x'])assert.equal((await call(request(name),e)).status,404);
 assert.equal((await call(request('latest.json','PUT','abc','a'.repeat(64)),e)).status,404);
 const sha=await hash(new TextEncoder().encode('abc'));assert.equal((await call(request(undefined,'PUT','abc',sha,{'content-length':'2'}),e)).status,503);assert.equal(e.BACKUPS.objects.size,0);
 assert.equal((await sfcBackup(request(undefined,'PUT','abc',sha),e)).status,429);
 assert.equal((await call(request(undefined,'PUT','abc',sha,{'x-source-expires-at':String(Date.now()+90000000)}),e)).status,400);
});
test('candidate and unverified accepted manifests never advance recovery',async()=>{
 const {e,sha}=await uploaded();assert.equal((await putManifest(e,manifest(sha,'candidate'))).status,200);assert.equal(e.BACKUPS.objects.has('curated/sfc/latest.json'),false);
 const other=await uploaded();assert.equal((await putManifest(other.e,{...manifest(other.sha),acceptedPointerIncluded:false})).status,409);assert.equal(other.e.BACKUPS.objects.has('curated/sfc/latest.json'),false);
});
test('accepted recovery requires its verified immutable dump and expected predecessor',async()=>{
 const {e,sha}=await uploaded();const m=manifest(sha);assert.equal((await putManifest(e,m)).status,200);assert.equal((await putManifest(e,m)).status,200);
 const latest=await (await call(request('latest.json'),e)).json();assert.equal(latest.version,m.version);
 const {e:conflict,sha:s}=await uploaded();await conflict.BACKUPS.put('curated/sfc/latest.json',JSON.stringify({manifestSha256:'d'.repeat(64)}),{customMetadata:{expiresAt:String(expires)}});assert.equal((await putManifest(conflict,manifest(s))).status,409);assert.equal((await (await call(request('latest.json'),conflict)).json()).manifestSha256,'d'.repeat(64));
 assert.equal(e.BACKUPS.objects.has('curated/hkex-daily/latest.json'),false);assert(e.BACKUPS.objects.has(SFC_PREFIX+stamp+'/source.dump'));
});
test('SFC admission survives controller recreation with a separate daily byte ledger',()=>{
 const db=new DatabaseSync(':memory:'),sql={exec(q,...args){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...args):(s.run(...args),[]);}},now=Date.UTC(2026,9,27);
 for(let n=0;n<4;n++)assert.equal(sfcBackupAdmission(sql,MAX_SFC_DUMP,true,now),true);assert.equal(sfcBackupAdmission(sql,1,true,now),false);assert.equal(sfcBackupAdmission(sql,1,true,now+86400000),true);assert.equal(sfcBackupAdmission(sql,MAX_SFC_DUMP+1,true,now),false);
});
