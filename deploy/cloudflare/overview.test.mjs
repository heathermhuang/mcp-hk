import assert from 'node:assert/strict';
import {test} from 'node:test';
import {compactOverview, saveOverview, serveOverview, OVERVIEW_KEY} from './overview.ts';
const coverage={generation:'accepted-generation',datasets:{discovered:4984},resources:{discovered:63360,byStatus:{queryable:40765}},privateField:'not-public'};
function env(initial=null,failed=false) {
  let stored=initial;
  return {get APP(){throw Error('Landing overview must never use the container');},RELEASE_COMMIT:'checked-release',BACKUPS:{async get(key){assert.equal(key,OVERVIEW_KEY);if(failed)throw Error('storage unavailable');return stored ? {body:new Blob([stored]).stream()} : null;},async put(key,value){assert.equal(key,OVERVIEW_KEY);stored=value;}},ASSETS:{async fetch(request){assert.equal(new URL(request.url).pathname,'/overview.json');return Response.json({...compactOverview(coverage),asOf:'2026-10-16T00:00:00Z'});}}};
}
test('published homepage counts do not access a sleeping/unavailable container',async()=>{
  const e=env();await saveOverview(e,coverage);
  const r=await serveOverview(e,new Request('https://mcp.hk/assets/overview.json'));const body=await r.json();
  assert.equal(body.resources.byStatus.queryable,40765);assert.equal(body.allGovernmentDataConnected,false);assert.equal(body.privateField,undefined);assert.ok(body.asOf);
  assert.equal(r.headers.get('x-mcp-overview'),'published');assert.equal(r.headers.get('cache-control'),'public, max-age=60');
});
test('missing or failed R2 returns a dated release snapshot without querying the backend',async()=>{
  for(const e of [env(),env(null,true)]) {
    const r=await serveOverview(e,new Request('https://mcp.hk/assets/overview.json'));
    assert.equal(r.headers.get('x-mcp-overview'),'release-snapshot');assert.equal((await r.json()).asOf,'2026-10-16T00:00:00Z');
  }
});
test('invalid updates retain the last published counts',async()=>{
  const e=env();await saveOverview(e,coverage);
  for(const invalid of [{...coverage,resources:{discovered:2,byStatus:{queryable:3}}},{...coverage,datasets:{discovered:-1}},{...coverage,generation:''}]) await assert.rejects(saveOverview(e,invalid));
  assert.equal((await (await serveOverview(e,new Request('https://mcp.hk/assets/overview.json'))).json()).datasets.discovered,4984);
});
test('overview endpoint is read-only and HEAD has no response body',async()=>{
  const e=env();assert.equal((await serveOverview(e,new Request('https://mcp.hk/assets/overview.json',{method:'POST'}))).status,405);
  assert.equal(await (await serveOverview(e,new Request('https://mcp.hk/assets/overview.json',{method:'HEAD'}))).text(),'');
});
