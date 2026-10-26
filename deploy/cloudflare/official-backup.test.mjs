import {test} from 'node:test';
import assert from 'node:assert/strict';
import {officialBackup as handler,officialBackupAdmission,OFFICIAL_PREFIX,MAX_OFFICIAL_DUMP} from './official-backup.ts';
import {DatabaseSync} from 'node:sqlite';
import {createHash} from 'node:crypto';
if(!crypto.DigestStream)crypto.DigestStream=class extends WritableStream{
 constructor(){const hash=createHash('sha256');let resolve,reject;const digest=new Promise((yes,no)=>{resolve=yes;reject=no;});super({write(chunk){hash.update(chunk);},close(){resolve(hash.digest());},abort(error){reject(error);}});this.digest=digest;}
};
const officialBackup=(request,env)=>handler(request,env,async()=>true);
const token='u'.repeat(48),stamp='20261024T120000Z-1234abcd';
function request(path=stamp+'/official.dump',method='GET',headers={}){return new Request('https://mcp.hk/__company-backup/'+path,{method,headers:{authorization:'Bearer '+token,...headers},...(method==='PUT'?{body:'abc'}:{})});}
function bucket(){const objects=new Map();return {objects,async head(k){return objects.get(k)||null;},async get(k){return objects.get(k)||null;},async put(k,body,options){if(objects.has(k))return null;const bytes=new Uint8Array(await new Response(body).arrayBuffer());const sha=Buffer.from(await crypto.subtle.digest('SHA-256',bytes)).toString('hex');if(sha!==options.sha256)throw new Error('checksum');const value={size:bytes.length,get body(){return new Blob([bytes]).stream();},customMetadata:options.customMetadata};objects.set(k,value);return value;}};}
test('official backup capability is absent without a dedicated credential and never uses OPS token',async()=>{const BACKUPS=bucket();for(const env of [{BACKUPS},{BACKUPS,OPS_TOKEN:token},{BACKUPS,OPS_TOKEN:token,OFFICIAL_BACKUP_TOKEN:token},{BACKUPS,OFFICIAL_BACKUP_TOKEN:'short'}])assert.equal((await officialBackup(request(),env)).status,404);assert.equal(BACKUPS.objects.size,0);});
test('official backup capability restricts origin, exact prefix, names and methods',async()=>{const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token};for(const path of ['../latest.snapshot.tar.gz',stamp+'/arbitrary.dump',stamp+'/official.dump/extra','latest.json',stamp+'/official.dump?token=x'])assert.equal((await officialBackup(request(path),env)).status,404);for(const method of ['DELETE','POST','PATCH'])assert.equal((await officialBackup(request(undefined,method),env)).status,404);const other=new Request('https://example.com/__company-backup/'+stamp+'/official.dump',{headers:{authorization:'Bearer '+token}});assert.equal((await officialBackup(other,env)).status,404);});
test('official backup upload verifies bytes and is immutable; HEAD/GET are scoped',async()=>{const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token};const sha=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode('abc'))).toString('hex');const headers={'content-length':'3','x-object-sha256':sha};assert.equal((await officialBackup(request(undefined,'PUT',headers),env)).status,200);assert.equal((await officialBackup(request(undefined,'PUT',headers),env)).status,409);assert.equal(env.BACKUPS.objects.size,1);assert(env.BACKUPS.objects.has(OFFICIAL_PREFIX+stamp+'/official.dump'));const read=await officialBackup(request(),env);assert.equal(await read.text(),'abc');assert.equal((await officialBackup(request(undefined,'HEAD'),env)).headers.get('x-object-sha256'),sha);});
test('oversize and checksum failure do not create an offsite object or recovery pointer',async()=>{const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token};assert.equal((await officialBackup(request(undefined,'PUT',{'content-length':String(MAX_OFFICIAL_DUMP+1),'x-object-sha256':'a'.repeat(64)}),env)).status,400);assert.equal((await officialBackup(request(undefined,'PUT',{'content-length':'3','x-object-sha256':'a'.repeat(64)}),env)).status,503);assert.equal(env.BACKUPS.objects.size,0);});

test('backup admission is durable, aggregate and bounds bytes independently of object names',()=>{
 const db=new DatabaseSync(':memory:');const sql={exec(query,...values){const stmt=db.prepare(query);return /^SELECT/i.test(query)?stmt.all(...values):(stmt.run(...values),[]);}};const now=Date.UTC(2026,9,24);
 for(let i=0;i<4;i++)assert.equal(officialBackupAdmission(sql,MAX_OFFICIAL_DUMP,true,now),true);
 assert.equal(officialBackupAdmission(sql,MAX_OFFICIAL_DUMP,true,now),false);
 assert.equal(officialBackupAdmission(sql,MAX_OFFICIAL_DUMP,true,now+86400000),true);
 for(let i=0;i<8;i++)assert.equal(officialBackupAdmission(sql,MAX_OFFICIAL_DUMP,false,now),true);
 assert.equal(officialBackupAdmission(sql,1,false,now),false);
});
test('an unavailable admission authority fails closed before storing bytes',async()=>{
 const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token};
 assert.equal((await handler(request(undefined,'PUT',{'content-length':'3','x-object-sha256':'a'.repeat(64)}),env)).status,429);
 assert.equal(env.BACKUPS.objects.size,0);
});

test('a recovery manifest cannot precede the exact checksum-verified dependencies',async()=>{
 const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token};const sha=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode('abc'))).toString('hex');
 const payload=JSON.stringify({prefix:OFFICIAL_PREFIX+stamp,artifacts:{'official.dump':{sha256:sha,bytes:3},'source.json':{sha256:sha,bytes:3}}});const hash=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(payload))).toString('hex');
 const manifest=()=>new Request('https://mcp.hk/__company-backup/'+stamp+'/manifest.json',{method:'PUT',headers:{authorization:'Bearer '+token,'content-length':String(payload.length),'x-object-sha256':hash},body:payload});
 assert.equal((await officialBackup(manifest(),env)).status,409);
 assert.equal(env.BACKUPS.objects.size,0);
 for(const name of ['official.dump','source.json'])assert.equal((await officialBackup(request(stamp+'/'+name,'PUT',{'content-length':'3','x-object-sha256':sha}),env)).status,200);
 assert.equal((await officialBackup(manifest(),env)).status,200);
});

const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
function put(path,bytes){return new Request('https://mcp.hk/__company-backup/'+stamp+'/'+path,{method:'PUT',headers:{authorization:'Bearer '+token,'content-length':String(Buffer.byteLength(bytes)),'x-object-sha256':sha(bytes)},body:bytes});}
async function partsFixture(){
 const env={BACKUPS:bucket(),OFFICIAL_BACKUP_TOKEN:token},chunks=['abc','def'];
 for(let i=0;i<chunks.length;i++)assert.equal((await officialBackup(put(`official.part-${String(i).padStart(3,'0')}`,chunks[i]),env)).status,200);
 assert.equal((await officialBackup(put('source.json','{}'),env)).status,200);
 const dump={bytes:6,sha256:sha('abcdef'),parts:chunks.map((c,i)=>({name:`official.part-${String(i).padStart(3,'0')}`,bytes:c.length,sha256:sha(c)}))};
 return {env,dump,manifest:{prefix:OFFICIAL_PREFIX+stamp,artifacts:{'official.dump':dump,'source.json':{bytes:2,sha256:sha('{}')}}}};
}
test('bounded dump parts require an independently streamed whole-dump checksum; legacy HEAD/GET reconstruct it',async()=>{
 const {env,manifest}=await partsFixture();assert.equal((await officialBackup(request(),env)).status,404,'incomplete parts are not a published recovery object');
 assert.equal((await officialBackup(put('manifest.json',JSON.stringify(manifest)),env)).status,200);
 assert.equal(env.BACKUPS.objects.has(OFFICIAL_PREFIX+stamp+'/official.dump'),false);
 const head=await officialBackup(request(undefined,'HEAD'),env);assert.equal(head.status,200);assert.equal(head.headers.get('content-length'),'6');assert.equal(head.headers.get('x-object-sha256'),sha('abcdef'));
 const response=await officialBackup(request(),env);assert.equal(response.status,200);assert.equal(await response.text(),'abcdef');
});
test('missing, reordered, duplicate, oversize and wrong aggregate dump parts cannot publish a recovery manifest',async()=>{
 for(const change of [m=>m.artifacts['official.dump'].sha256='0'.repeat(64),m=>m.artifacts['official.dump'].parts.reverse(),m=>m.artifacts['official.dump'].parts.push(m.artifacts['official.dump'].parts[0]),m=>m.artifacts['official.dump'].bytes=7,m=>m.artifacts['official.dump'].parts[0].bytes=64*1024*1024+1]){
  const {env,manifest}=await partsFixture();change(manifest);assert.notEqual((await officialBackup(put('manifest.json',JSON.stringify(manifest)),env)).status,200);assert.equal(env.BACKUPS.objects.has(OFFICIAL_PREFIX+stamp+'/manifest.json'),false);
 }
 const {env,manifest}=await partsFixture();env.BACKUPS.objects.delete(OFFICIAL_PREFIX+stamp+'/official.part-001');assert.equal((await officialBackup(put('manifest.json',JSON.stringify(manifest)),env)).status,409);
 assert.equal((await officialBackup(put('official.part-004','abc'),env)).status,404);
});
