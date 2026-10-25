import assert from 'node:assert/strict';
import {test} from 'node:test';
import {DatabaseSync} from 'node:sqlite';
import {UsageStore,clientKey,describeRequest,inspectResponse,meterResponse,LIMITS} from './usage.ts';
const now = Date.UTC(2026,9,17,10,0,10), rid='e34a14f5c386e36b39bdbcadfa1dda15';
function store(){const db=new DatabaseSync(':memory:');const sql={exec(query,...values){const statement=db.prepare(query);return /^SELECT/i.test(query)?statement.all(...values):(statement.run(...values),[]);}};return {db,sql,usage:new UsageStore(sql)};}
const op={protocol:'mcp',operation:'hk_resource_query',resource:rid,dataset:'',sourceCalls:0};
test('global durable quota rejects the 61st request and resets at the actual minute',()=>{
  const {usage}=store();for(let i=0;i<60;i++)assert.equal(usage.quota('daily-hash',0,now).allowed,true);
  assert.equal(usage.quota('daily-hash',0,now,false).allowed,false);
  const denied=usage.quota('daily-hash',0,now);assert.equal(denied.allowed,false);assert.equal(denied.retryAfter,50);
  assert.equal(usage.quota('daily-hash',0,now+50000).allowed,true);
  assert.equal(usage.quota('other-hash',0,now).allowed,true);
  for(let i=0;i<100;i++)assert.equal(usage.quota('preview-only',0,now,false).allowed,true);
  assert.equal(usage.quota('preview-only',0,now).remaining,59);
});
test('shared daily source/request budgets cannot be bypassed by changing client key',()=>{
  const {db,usage}=store(),day=Math.floor(now/86400000);
  db.prepare('INSERT INTO daily VALUES (?,?,?)').run(day,10,10000);
  assert.equal(usage.quota('new-client',1,now).scope,'shared_daily_budget');
  assert.equal(usage.quota('new-client',0,now).allowed,true);
  db.prepare('UPDATE daily SET calls=50000 WHERE day=?').run(day);
  assert.equal(usage.quota('another-client',0,now).allowed,false);
});
test('client quota keys are secret-dependent, daily HMAC values without the IP',async()=>{
  const a=await clientKey('203.0.113.3','test-secret',now);
  assert.match(a,/^[a-f0-9]{64}$/);assert.notEqual(a,await clientKey('203.0.113.3','other-secret',now));
  assert.notEqual(a,await clientKey('203.0.113.3','test-secret',now+86400000));
});
test('request dimensions omit search text, coordinates, arbitrary tool names and extra arguments',()=>{
  const body=new TextEncoder().encode(JSON.stringify({method:'tools/call',params:{name:'hk_resource_query',arguments:{resourceId:rid,q:'private query',lat:22.3}}}));
  assert.deepEqual(describeRequest(new Request('https://mcp.hk/mcp'),body),op);
  assert.doesNotMatch(JSON.stringify(describeRequest(new Request('https://mcp.hk/api/v1/addresses/search?q=private-query&lat=22.3'))),/private|22\.3/);
  assert.equal(describeRequest(new Request('https://mcp.hk/mcp'),new TextEncoder().encode('{"method":"tools/call","params":{"name":"a-secret"}}')).operation,'other');
});
test('MCP tool errors are errors despite HTTP 200, and returned counts never use dataset total',()=>{
  assert.equal(inspectResponse('data: '+JSON.stringify({result:{isError:true,content:[{text:'sensitive error'}]}})+'\n\n',op,200).outcome,'error');
  assert.equal(inspectResponse(': keepalive\n\nevent: message\ndata: {"method":"notifications/progress","params":{"progress":1}}\n\nevent: message\ndata: {"result":{"isError":true}}\n\n',op,200).outcome,'error');
  const payload={resource:{id:rid,datasetId:'ff-fortune-schedule2'},data:{items:[{eta:'12:00'},{eta:'12:10'}]},meta:{total:10000}};
  const result=inspectResponse(JSON.stringify({result:{structuredContent:payload}}),op,200);
  assert.equal(result.items,2);assert.equal(result.op.dataset,'ff-fortune-schedule2');
  assert.equal(inspectResponse(JSON.stringify({result:{structuredContent:{data:{items:[]},provenance:[{sourceId:'restaurants'}]}}}),op,200).op.dataset,'restaurants');
});
test('stream accounting preserves UTF-8 payload and counts exact observed body bytes',async()=>{
  const bytes=new TextEncoder().encode(JSON.stringify({result:{structuredContent:{data:{items:[{name:'港產🚢'}]}}}}));let saved;
  const stream=new ReadableStream({start(c){c.enqueue(bytes.slice(0,50));c.enqueue(bytes.slice(50));c.close();}});
  const metered=meterResponse(new Response(stream),op,42,Date.now(),(...args)=>{saved=args;});
  assert.deepEqual(new Uint8Array(await metered.response.arrayBuffer()),bytes);await metered.done;
  assert.equal(saved[4],bytes.length);assert.equal(saved[3],42);assert.equal(saved[5],1);
});
test('large/unknown responses and cancellations do not invent returned-item counts',async()=>{
  let saved;const bytes=new Uint8Array(300000);
  const a=meterResponse(new Response(bytes),op,0,Date.now(),(...args)=>{saved=args;});await a.response.arrayBuffer();await a.done;
  assert.equal(saved[4],300000);assert.equal(saved[5],null);assert.equal(saved[2],'uninspected');
  const b=meterResponse(new Response(new ReadableStream({pull(c){c.enqueue(new Uint8Array(5));}})),op,0,Date.now(),(...args)=>{saved=args;});
  const reader=b.response.body.getReader();await reader.read();await reader.cancel();await b.done;assert.equal(saved[2],'cancelled');assert.equal(saved[5],null);
});
test('aggregate retention, restart persistence, byte totals and throttles are reportable without identities',()=>{
  const {db,sql,usage}=store();usage.record(op,200,'error',42,100,0,12,now);usage.record(op,429,'rate_limited',10,30,0,2,now);
  usage.record(op,200,'ok',10,50,2,3,now-91*86400000);
  const report=new UsageStore(sql).report(90,now);assert.equal(report.totals.requests,2);assert.equal(report.totals.response_bytes,130);
  assert.equal(report.rows.length,2);assert.equal(db.prepare('SELECT count(*) n FROM usage_daily').get().n,2);
  assert.doesNotMatch(JSON.stringify(report.rows),/private-query|203\.0\.113|test-secret/);
  assert.equal(report.limits.perMinute,LIMITS.perMinute);
});

test('SeeHouse operations retain only bounded names and count returned rows, never coverage totals',()=>{
  for(const name of ['hk_property_search','hk_property_building','hk_property_price_history','hk_property_coverage']){
    const body=new TextEncoder().encode(JSON.stringify({method:'tools/call',params:{name,arguments:{q:'private query',buildingId:'private-id'}}}));
    const described=describeRequest(new Request('https://mcp.hk/mcp'),body);
    assert.equal(described.operation,name);assert.doesNotMatch(JSON.stringify(described),/private/);
  }
  assert.equal(describeRequest(new Request('https://mcp.hk/api/v1/properties/building?buildingId=private-id')).operation,'properties');
  for(const key of ['candidates','listings','events']){
    const result=inspectResponse(JSON.stringify({data:{[key]:[{},{}]},meta:{total:999},provenance:[{sourceId:'seehouse'}]}),{...op,protocol:'http'},200);
    assert.equal(result.items,2);assert.equal(result.op.dataset,'seehouse');
  }
});

test('racing counts returned result rows rather than coverage denominators',()=>{
 const op={protocol:'http',operation:'racing',dataset:'racing',resource:'',sourceCalls:0};
 assert.equal(inspectResponse(JSON.stringify({data:{results:[{},{}]},coverage:{resultRows:100000}}),op,200).items,2);
});
