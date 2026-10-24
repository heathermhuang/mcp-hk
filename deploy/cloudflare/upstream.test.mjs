import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {test} from 'node:test';
import {UpstreamStore,UPSTREAM,governedFetch,closeOperation,upstreamTarget,dispatchOperation} from './upstream.ts';
function fixture(calls=10000,bytes=100_000_000){
  const db=new DatabaseSync(':memory:');let now=Date.UTC(2026,9,24,5);
  const sql={exec(q,...v){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...v):(s.run(...v),[]);}};
  const atomic=fn=>{db.exec('BEGIN');try{const r=fn();db.exec('COMMIT');return r;}catch(e){db.exec('ROLLBACK');throw e;}};
  const store=new UpstreamStore(sql,atomic,calls,bytes,()=>now);
  return {db,sql,atomic,store,advance:ms=>{now+=ms;},restart:()=>new UpstreamStore(sql,atomic,calls,bytes,()=>now)};
}
const req=(id,target='https://data.gov.hk/data',path='/fetch',method='GET')=>new Request('http://mcp-egress'+path,{method,headers:{'x-mcp-operation':id,'x-mcp-target':target,Authorization:'Bearer caller-secret',Cookie:'private'}});
test('edge exhausted allocations deny before dispatch or any upstream effects and retain across restart/day rollover',async()=>{
  const f=fixture(100,8_000_000);let dispatches=0,fetches=0;
  const backend=async request=>{dispatches++;const id=request.headers.get('x-mcp-operation');f.store.claim(id);return governedFetch(req(id),f.store,'',undefined,async()=>{fetches++;return new Response('ok');});};
  const first=await dispatchOperation(new Request('https://mcp.hk/api/v1/addresses/search'),f.store,backend);assert.equal(first.status,200);await first.text();
  assert.equal(dispatches,1);assert.equal(fetches,1);
  const denied=await dispatchOperation(new Request('https://mcp.hk/api/v1/addresses/search'),f.store,backend);assert.equal(denied.status,429);assert.equal(dispatches,1);assert.equal(fetches,1);
  assert.throws(()=>f.restart().reserve(),/ALLOCATION_EXHAUSTED/);
  f.advance(86400000);assert.ok(f.restart().reserve());
});
test('parallel reservations cannot overcommit; cache completion refunds zero upstream; unknown/cancelled work keeps reservation',async()=>{
  const f=fixture(200,16_000_000);
  const reservations=await Promise.allSettled(Array.from({length:8},async()=>f.store.reserve()));
  assert.equal(reservations.filter(r=>r.status==='fulfilled').length,2);
  const [a,b]=reservations.filter(r=>r.status==='fulfilled').map(r=>r.value);
  f.store.finish(a,true);assert.ok(f.store.reserve());
  f.store.finish(b,false);
  assert.throws(()=>f.store.reserve(),/ALLOCATION_EXHAUSTED/);
  assert.equal(f.store.report().daily[0].observed_calls,0);assert.equal(f.store.report().daily[0].observed_bytes,0);
});
test('missing forged expired and replayed grants fail, failures remain charged, call cap prevents request 101',async()=>{
  const f=fixture();let effects=0;
  const fetcher=async()=>{effects++;return new Response('abc');};
  for(const id of ['','forged'])assert.equal((await governedFetch(req(id),f.store,'',undefined,fetcher)).status,429);
  const id=f.store.reserve();assert.equal((await governedFetch(req(id,undefined,'/claim','POST'),f.store,'',undefined,fetcher)).status,204);
  assert.equal((await governedFetch(req(id,undefined,'/claim','POST'),f.store,'',undefined,fetcher)).status,429);
  assert.equal((await governedFetch(req(id),f.store,'',undefined,async()=>{effects++;throw Error('failure');})).status,502);
  for(let i=1;i<UPSTREAM.calls;i++)assert.equal(await (await governedFetch(req(id),f.store,'',undefined,fetcher)).text(),'abc');
  const count=effects;assert.equal((await governedFetch(req(id),f.store,'',undefined,fetcher)).status,429);assert.equal(effects,count);
  assert.equal(f.store.report().daily[0].observed_calls,100);
  f.advance(30001);assert.equal((await governedFetch(req(id),f.store,'',undefined,fetcher)).status,429);assert.equal(effects,count);
});
test('edge byte and concurrency limits cancel at boundary and strip accounting and caller credentials',async()=>{
  const f=fixture(),id=f.store.reserve();f.store.claim(id);
  f.db.prepare('UPDATE upstream_grants SET max_bytes=4 WHERE id=?').run(id);
  let cancelled=false,seen;
  const fetcher=async(url,init)=>{seen=init;return new Response(new ReadableStream({start(c){c.enqueue(new Uint8Array([1,2,3]));c.enqueue(new Uint8Array([4,5,6]));},cancel(){cancelled=true;}}));};
  const result=await governedFetch(req(id),f.store,'',undefined,fetcher);
  await assert.rejects(result.arrayBuffer(),/UPSTREAM_BYTES/);assert.equal(cancelled,true);
  assert.equal(seen.redirect,'manual');for(const key of ['Authorization','Cookie','x-mcp-operation','x-mcp-target'])assert.equal(seen.headers.has(key),false);
  assert.equal(f.store.report().daily[0].observed_bytes,6);
  const next=f.store.reserve();f.store.claim(next);f.store.begin(next);f.store.begin(next);assert.throws(()=>f.store.begin(next),/UPSTREAM_BUDGET/);
});
test('upstream response decoding, partial cancellation, end-of-operation invalidation and exact curated auth target',async()=>{
  const f=fixture(),id=f.store.reserve();f.store.claim(id);
  const compressed=new Blob(['publisher data']).stream().pipeThrough(new CompressionStream('gzip'));
  let headers;
  const response=await governedFetch(req(id,'https://curated.mcp.hk/v1/companies'),f.store,'https://curated.mcp.hk','scoped-token',async(url,init)=>{headers=init.headers;return new Response(compressed,{headers:{'Content-Encoding':'gzip'}});});
  assert.equal(await response.text(),'publisher data');assert.equal(headers.get('Authorization'),'Bearer scoped-token');assert.equal(f.store.report().daily[0].observed_bytes,14);
  const completed=closeOperation(new Response('done'),known=>f.store.finish(id,known));await completed.text();assert.throws(()=>f.store.begin(id),/INVALID_OPERATION/);
  for(const url of ['http://127.0.0.1','http://169.254.169.254','https://[::1]','https://user:pass@example.com','https://example.com:444','http://example.internal'])assert.throws(()=>upstreamTarget(url));
});


test('cancelling an operation retains global in-flight allocation until source cleanup and rejects oversized gateway POST',async()=>{
 const f=fixture(),a=f.store.reserve();f.store.claim(a);f.store.begin(a);f.store.finish(a,false);
 assert.equal(f.db.prepare('SELECT inflight FROM upstream_grants WHERE id=?').get(a).inflight,1);
 let effects=0;const b=f.store.reserve();f.store.claim(b);
 const response=await governedFetch(new Request('http://mcp-egress/fetch',{method:'POST',headers:{'x-mcp-operation':b,'x-mcp-target':'https://data.gov.hk/data'},body:new Uint8Array(65537)}),f.store,'',undefined,async()=>{effects++;return new Response('unexpected');});
 assert.equal(response.status,502);assert.equal(effects,0);
 const cancelled=closeOperation(new Response('data'),known=>f.store.finish(b,known));await cancelled.body.cancel();assert.throws(()=>f.store.claim(b),/INVALID_OPERATION/);
});


test('whole upstream deadline cancels a stalled body even when synthetic fetch ignores its abort signal',async()=>{
 const f=fixture(),id=f.store.reserve();f.store.claim(id);let cancelled=false;
 f.db.prepare('UPDATE upstream_grants SET expires=expires-29990 WHERE id=?').run(id);
 const response=await governedFetch(req(id),f.store,'',undefined,async()=>new Response(new ReadableStream({pull(){return new Promise(()=>{});},cancel(){cancelled=true;}})));
 await assert.rejects(response.arrayBuffer(),/UPSTREAM_DEADLINE/);assert.equal(cancelled,true);
 assert.equal(f.store.report().daily[0].observed_calls,1);
});
