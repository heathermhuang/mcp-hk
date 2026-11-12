import assert from 'node:assert/strict';
import {test} from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';
import vm from 'node:vm';
import {IntelligenceStore,ANALYTICS_LIMITS,datasetFamily,reportingDay,networkHash,requestFacts,safeKeyword,optedOut} from './intelligence.ts';
import {describeRequest,inspectResponse,meterResponse,operationNames} from './usage.ts';
import {dataRequestHeaders} from './agent-auth.ts';

const now=Date.UTC(2026,10,12,2),day=reportingDay(now);
function fixture(size=()=>0){
  const db=new DatabaseSync(':memory:');
  const sql={exec(q,...args){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...args):(s.run(...args),[]);}};
  const transaction=fn=>{db.exec('BEGIN');try{const result=fn();db.exec('COMMIT');return result;}catch(e){db.exec('ROLLBACK');throw e;}};
  return {db,sql,store:new IntelligenceStore(sql,transaction,size),transaction};
}
function event(at=now,extra={}){
  const req=new Request('https://mcp.hk/api/v1/catalogue/datasets?q=air%20quality');
  const op=describeRequest(req);
  return {id:crypto.randomUUID(),at,op,facts:requestFacts(req,op),result:{category:'nonempty',stale:false,version:'v1',hasMore:false},status:200,outcome:'ok',items:2,bytesIn:0,bytesOut:100,duration:25,...extra};
}
test('actual registered MCP tool names cannot silently fall into other',()=>{
  const root=new URL('../../src/mcp_open_data_hk/',import.meta.url),names=new Set();
  for(const file of readdirSync(root).filter(f=>f.endsWith('.py'))){
    for(const match of readFileSync(new URL(file,root),'utf8').matchAll(/(?:async )?def (hk_\w+)\(/g))names.add(match[1]);
  }
  for(const name of names)assert.ok(operationNames.includes(name),name);
  for(const [operation,pack] of [['hk_company_search','companies'],['hk_hkex_archive_disclosures','webb-sdi'],['hk_hkex_latest_disclosures','hkex-daily'],['hk_sfc_verify','sfc'],['hk_transport_journey','transport'],['hk_racing_results','racing']])assert.equal(datasetFamily(operation),pack);
  assert.equal(datasetFamily('other'),'');
});
test('public catalogue keywords are bounded and sensitive operations/values are suppressed',()=>{
  assert.equal(safeKeyword('  空氣   質素 '),'空氣 質素');
  for(const value of ['name@example.com','https://secret.example','password abc','123456789','a'.repeat(32),'x'.repeat(161)])assert.equal(safeKeyword(value),null,value);
  const req=new Request('https://mcp.hk/mcp');
  const body=new TextEncoder().encode(JSON.stringify({method:'tools/call',params:{name:'hk_address_search',arguments:{q:'Private home address'}}}));
  assert.equal(requestFacts(req,describeRequest(req,body),body).keyword,null);
});
test('explicit browser refusal reaches the backend after credentials are stripped',()=>{
  for(const headers of [{Cookie:'session=secret; __Host-mhk_analytics=off'},{DNT:'1'},{'Sec-GPC':'1'},{'x-mcp-analytics-opt-out':'1'}]){
    const req=new Request('https://mcp.hk/api/v1/catalogue/datasets?q=schools',{headers:{Authorization:'Bearer secret',...headers}});
    const forwarded=dataRequestHeaders(req,'203.0.113.1');
    assert.equal(forwarded.get('Authorization'),null);assert.equal(forwarded.get('Cookie'),null);assert.equal(forwarded.get('x-mcp-analytics-opt-out'),'1');
    const clean=new Request(req.url,{headers:forwarded}),facts=requestFacts(clean,describeRequest(clean));
    assert.equal(optedOut(clean),true);assert.equal(facts.detail,false);assert.equal(facts.keyword,null);assert.equal(facts.client,'unknown');
  }
});
test('browser migration sets refusal before requests and never creates affirmative consent',()=>{
  let saved=JSON.stringify({version:1,allowed:false,at:1}),cookie='';const listeners={};
  const document={get cookie(){return cookie;},set cookie(v){cookie=v;}};
  const context=vm.createContext({document,navigator:{},location:new URL('https://mcp.hk'),localStorage:{getItem:()=>saved}});
  context.window=context;context.addEventListener=(k,fn)=>listeners[k]=fn;
  vm.runInContext(readFileSync(new URL('../../src/mcp_open_data_hk/web/privacy-signal.js',import.meta.url),'utf8'),context);
  assert.match(cookie,/__Host-mhk_analytics=off/);assert.equal(context.MhkPrivacy.headers()['x-mcp-analytics-opt-out'],'1');
  context.MhkPrivacy.sync(true);assert.match(cookie,/Max-Age=0/);
  listeners.storage({});assert.match(cookie,/__Host-mhk_analytics=off/);
  saved=null;listeners.storage({});assert.deepEqual(Object.keys(context.MhkPrivacy.headers()),[]);assert.match(cookie,/Max-Age=0/);
});
test('network pseudonyms are independent of quotas and change at Hong Kong midnight',async()=>{
  const midnight=Date.UTC(2026,10,12,16);
  const a=await networkHash('203.0.113.1','analytics-only',midnight-1);
  assert.notEqual(a,await networkHash('203.0.113.1','analytics-only',midnight));
  assert.equal(await networkHash('unknown','analytics-only',now),null);
  assert.equal(await networkHash('203.0.113.1','analytics-only',now),await networkHash('203.0.113.1','analytics-only',now+1000));
});
test('client identity is per-request self-report; initialization does not label future stateless calls',()=>{
  const req=new Request('https://mcp.hk/mcp');
  const body=new TextEncoder().encode(JSON.stringify({method:'initialize',params:{clientInfo:{name:'Claude',version:'secret'}}}));
  assert.equal(requestFacts(req,describeRequest(req,body),body).client,'claude');
  assert.equal(requestFacts(req,describeRequest(req)).client,'unknown');
  assert.doesNotMatch(JSON.stringify(requestFacts(req,describeRequest(req,body),body)),/secret/);
});
test('storage is transactional, idempotent, restart-safe and does not persist network addresses',()=>{
  const f=fixture(),e=event();assert.equal(f.store.record(e,'hash',now).recorded,true);
  assert.equal(f.store.record(e,'hash',now).reason,'duplicate');
  const restarted=new IntelligenceStore(f.sql,f.transaction),r=restarted.report(7,now);
  assert.equal(r.totals.requests,1);assert.equal(r.audience[0].clients,1);assert.equal(r.health.collectionStart,String(now));
  assert.equal(r.recent[0].facts.keyword,'air quality');
  assert.doesNotMatch(JSON.stringify(r),/203\.0\.113/);
});
test('opted-out requests retain essential totals without keyword/client/event rows',()=>{
  const f=fixture(),e=event();e.facts={...e.facts,detail:false,keyword:null,keywordState:'opted_out',client:'unknown',clientEvidence:'opted_out'};
  f.store.record(e,null,now);const r=f.store.report(1,now);
  assert.equal(r.totals.requests,1);assert.equal(r.recent.length,0);assert.equal(r.keywords.length,0);assert.equal(r.audience[0].clients,0);assert.equal(r.audience[0].unresolved,1);
});
test('quota exhaustion and disk budgets stop analytics without unbounded event writes',()=>{
  const f=fixture();f.store.record(event(),'hash',now);
  f.db.prepare('UPDATE ai_budget SET minute_count=?').run(ANALYTICS_LIMITS.perMinute);
  assert.equal(f.store.record(event(),'other-hash',now).reason,'write_budget');
  assert.equal(f.store.report(1,now).totals.requests,1);assert.equal(f.store.report(1,now).budget[0].dropped,1);
  const full=fixture(()=>ANALYTICS_LIMITS.bytes+1);assert.equal(full.store.record(event(),null,now).reason,'storage_budget');assert.equal(full.store.report(1,now).totals.requests,0);
});
test('late popular keywords displace early rare terms within explicit Space-Saving bounds',()=>{
  const f=fixture();
  for(let i=0;i<ANALYTICS_LIMITS.keywordsPerDay+40;i++){
    const at=now+i*1000,e=event(at);e.facts.keyword='topic '+i;f.store.record(e,null,at);
  }
  for(let i=0;i<100;i++){const at=now+400000+i*1000,e=event(at);e.facts.keyword='late demand';f.store.record(e,null,at);}
  const r=f.store.report(1,now+500000),top=r.keywords[0];
  assert.equal(top.term,'late demand');assert.ok(top.lower_bound<=100);assert.ok(top.upper_bound>=100);
  assert.equal(f.db.prepare('SELECT count(*) n FROM ai_keywords').get().n,ANALYTICS_LIMITS.keywordsPerDay);
});
test('dimension and identity caps collapse excess without losing request totals',()=>{
  const f=fixture();
  const insert=f.db.prepare('INSERT INTO ai_dimensions VALUES (?,?,?,1,0,0)');
  for(let i=0;i<ANALYTICS_LIMITS.dimensionsPerDay;i++)insert.run(day,'dataset','resource-'+i);
  const client=f.db.prepare('INSERT INTO ai_clients VALUES (?,?)');for(let i=0;i<ANALYTICS_LIMITS.clientsPerDay;i++)client.run(day,'hash-'+i);
  f.store.record(event(),'new-hash',now);const r=f.store.report(1,now);
  assert.equal(r.totals.requests,1);assert.equal(r.audience[0].capped,1);
  assert.ok(f.db.prepare("SELECT count(*) n FROM ai_dimensions WHERE value='overflow'").get().n>0);
});
test('real failures cannot masquerade as no matches, including HTTP 200 MCP errors',()=>{
  const op={protocol:'mcp',operation:'hk_resource_query',resource:'',dataset:'',sourceCalls:0};
  const failed=inspectResponse(JSON.stringify({result:{isError:true,structuredContent:{error:{code:'UPSTREAM_TIMEOUT'}}}}),op,200);
  assert.equal(failed.summary.category,'source_unavailable');
  const empty=inspectResponse(JSON.stringify({result:{structuredContent:{data:{items:[]},meta:{total:900}}}}),op,200);
  assert.equal(empty.summary.category,'no_matches');assert.equal(empty.items,0);
  assert.equal(inspectResponse('invalid',op,200).summary.category,'unknown');
});
test('cancelled streams finalize once; an unavailable observer never changes response bytes',async()=>{
  let count=0;const bytes=new TextEncoder().encode('{"items":[]}');
  const a=meterResponse(new Response(bytes),event().op,0,Date.now(),()=>{},()=>{count++;throw Error('observer failed');});
  assert.deepEqual(new Uint8Array(await a.response.arrayBuffer()),bytes);await a.done;assert.equal(count,1);
  let category;const b=meterResponse(new Response(new ReadableStream({pull(c){c.enqueue(bytes);}})),event().op,0,Date.now(),()=>{},(...args)=>{category=args[7].category;});
  const reader=b.response.body.getReader();await reader.read();await reader.cancel();await b.done;assert.equal(category,'cancelled');
});
test('digest follows local days, waits until 09:00, survives duplicate ticks and catches up one day',()=>{
  const f=fixture(),start=Date.UTC(2026,10,10,17);f.store.record(event(start),null,start);
  const before=Date.UTC(2026,10,12,0,59),after=Date.UTC(2026,10,12,1);
  assert.equal(f.store.digest(before).reason,'not_due');assert.equal(f.store.digest(after).generated,true);
  assert.equal(f.store.digest(after).reason,'current');
  const digest=f.store.report(7,after).digests[0].body;
  assert.equal(digest.periodStart,'2026-11-10T16:00:00.000Z');assert.equal(digest.partial,true);
  assert.equal(digest.notification.status,'not_configured');
});
test('cleanup preserves aggregate history while removing expired recent identity and details',()=>{
  const f=fixture();f.store.record(event(),'hash',now);f.store.cleanup(now+9*86400000);
  const r=f.store.report(20,now+9*86400000);assert.equal(r.totals.requests,1);assert.equal(r.recent.length,0);
  assert.equal(f.db.prepare('SELECT count(*) n FROM ai_clients').get().n,0);assert.equal(r.audience[0].clients,1);
});
test('failed archives have at most three attempts per reporting day and remain visible',()=>{
  const f=fixture(),start=now-86400000;f.store.record(event(start),null,start);f.store.digest(now);
  for(let i=0;i<3;i++)assert.ok(f.store.nextArchive(now));
  assert.equal(f.store.nextArchive(now),null);
  assert.equal(f.store.report(7,now).archiveAttempts[0].count,3);
  assert.ok(f.store.nextArchive(now+86400000));
});
test('delayed completion across midnight keeps the event and network hash in the same reporting day',async()=>{
  const f=fixture(),midnight=Date.UTC(2026,10,12,16),at=midnight-1;
  const hash=await networkHash('203.0.113.1','analytics-only',at);
  f.store.record(event(at),hash,midnight+1);
  const r=f.store.report(2,midnight+1);
  assert.equal(r.audience[0].day,reportingDay(at));
  assert.equal(r.hours[0].hour,Math.floor(at/3600000));
  assert.equal(r.recent[0].at,at);
  assert.equal(r.budget[0].day,reportingDay(midnight+1));
});
test('event storage budget counts UTF-8 bytes rather than JavaScript characters',()=>{
  const f=fixture(),e=event();e.facts.keyword='香'.repeat(600);
  assert.ok(JSON.stringify(e).length<ANALYTICS_LIMITS.eventBytes);
  assert.equal(f.store.record(e,null,now).reason,'invalid');
});
