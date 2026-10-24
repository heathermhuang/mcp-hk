import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {companyDownloads,publishCompanyDownload} from './company-downloads.ts';

// Workerd's incremental DigestStream, with Node's independent streaming digest.
Object.defineProperty(crypto,'DigestStream',{value:class extends WritableStream{
 constructor(){const h=createHash('sha256');let resolve,reject;const digest=new Promise((a,b)=>{resolve=a;reject=b;});super({write:b=>h.update(b),close:()=>{const b=h.digest();resolve(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));},abort:reject});this.digest=digest;}
},configurable:true});
const sha=b=>createHash('sha256').update(b).digest('hex');
function fixture(){
 const content=new TextEncoder().encode('original archive bytes 香港'),hash=sha(content),notice=new TextEncoder().encode('David Webb original notice'),version='archive-v1',prefix=`exports/companies/${version}/${hash}`,map=new Map();
 const tables=['entities','entity_identifiers','entity_names','officer_appointments','licences','licence_relationships','source_references'].map(name=>({name,file:name+'.ndjson',rows:1,sha256:hash}));
 const value={formatVersion:1,version,view:'archive',scope:'complete_approved_subset',currentVerification:false,source:{counts:Object.fromEntries(tables.map(t=>[t.name,t.rows]))},schema:{},tables,noticeSha256:sha(notice),archive:{file:'companies.tar.gz',bytes:content.length,sha256:hash,parts:[{file:'part-000',bytes:content.length,sha256:hash}]}};
 const put=(k,v)=>map.set(k,typeof v==='string'?new TextEncoder().encode(v):v);
 put(prefix+'/part-000',content);put(prefix+'/manifest.json',JSON.stringify(value));put(prefix+'/NOTICE.txt',notice);put(`exports/companies/${version}/current.json`,JSON.stringify({version,sha256:hash}));put('exports/companies/latest.json',JSON.stringify({version,sha256:hash}));
 const bucket={async get(k){const v=map.get(k);return v?{size:v.length,body:new Response(v).body,arrayBuffer:async()=>v.buffer.slice(v.byteOffset,v.byteOffset+v.byteLength)}:null;},async head(k){const b=map.get(k);return b?{size:b.length}:null;},async put(k,v){put(k,v);}};
 return {content,hash,version,prefix,map,put,bucket,serve:companyDownloads(bucket),value};
}
const req=path=>new Request('https://mcp.hk'+path);
test('only approved immutable archive paths are served; manifest pins every download URL',async()=>{
 const f=fixture(),r=await f.serve(req('/downloads/companies/manifest.json?version=archive-v1'));assert.equal(r.status,200);const m=await r.json();assert.equal(m.archive.sha256,f.hash);const body=await f.serve(req(m.downloadUrl));assert.equal(body.headers.get('x-content-sha256'),f.hash);assert.equal(sha(new Uint8Array(await body.arrayBuffer())),f.hash);
 assert.equal((await f.serve(req('/downloads/companies/archive-v1/'+f.hash+'/../latest.snapshot.tar.gz'))).status,404);
 assert.equal((await f.serve(req('/downloads/companies/manifest.json?version=bad%2Fpath'))).status,400);
 assert.equal((await f.serve(req('/downloads/companies/missing/'+f.hash+'/manifest.json'))).status,404);
 assert.equal(await f.serve(req('/api/v1/companies')),null);
});
test('missing/truncated parts fail before response; corrupt same-size bytes abort instead of a successful file',async()=>{
 const a=fixture();a.map.delete(a.prefix+'/part-000');assert.equal((await a.serve(req(`/downloads/companies/${a.version}/${a.hash}/companies.tar.gz`))).status,503);
 const b=fixture();b.put(b.prefix+'/part-000',new Uint8Array(b.content.length).fill(42));const r=await b.serve(req(`/downloads/companies/${b.version}/${b.hash}/companies.tar.gz`));await assert.rejects(r.arrayBuffer(),/checksum/);
 const c=fixture();c.value.archive.bytes++;c.put(c.prefix+'/manifest.json',JSON.stringify(c.value));assert.equal((await c.serve(req('/downloads/companies/manifest.json'))).status,503);
});
test('two concurrent download slots are bounded and cancellation releases admission',async()=>{
 const f=fixture(),url=`/downloads/companies/${f.version}/${f.hash}/companies.tar.gz`,a=await f.serve(req(url)),b=await f.serve(req(url));assert.equal((await f.serve(req(url))).status,429);await a.body.cancel();const c=await f.serve(req(url));assert.equal(c.status,200);await b.body.cancel();await c.body.cancel();
});
test('publication refuses stale expected pointers or incomplete candidates without replacing the accepted pointer',async()=>{
 const f=fixture(),input={version:f.version,sha256:f.hash,expectedVersionHash:null,expectedLatestHash:null};await assert.rejects(publishCompanyDownload(f.bucket,input),/CONFLICT/);const before=f.map.get('exports/companies/latest.json').slice();f.map.delete(f.prefix+'/part-000');await assert.rejects(publishCompanyDownload(f.bucket,{...input,expectedVersionHash:f.hash,expectedLatestHash:f.hash}),/INCOMPLETE/);assert.deepEqual(f.map.get('exports/companies/latest.json'),before);
 const g=fixture();const result=await publishCompanyDownload(g.bucket,{...input,version:g.version,sha256:g.hash,expectedVersionHash:g.hash,expectedLatestHash:g.hash});assert.equal(result.published,true);
});
