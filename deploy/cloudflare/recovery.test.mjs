import assert from 'node:assert/strict';
import {test} from 'node:test';
import {normalizeBackendResponse} from './recovery.ts';
import {fetchPublicJson} from '../../src/mcp_open_data_hk/web/http.js';

test('plain proxy failures become bounded JSON recovery responses', async () => {
  const response=await normalizeBackendResponse(new Response('Failed to proxy request',{status:502}),'checked');
  assert.equal(response.status,503);assert.equal(response.headers.get('retry-after'),'10');assert.equal((await response.json()).error.code,'SERVICE_RECOVERING');
});
test('observed container cold-start HTTP 500 activates recovery without masking application errors', async () => {
  const response=await normalizeBackendResponse(new Response('Failed to start container: The container is not listening in the TCP address 10.0.0.1:8000',{status:500}),'cold-start');
  assert.equal(response.status,503);assert.equal(response.headers.get('Retry-After'),'10');
  assert.equal((await response.json()).error.code,'SERVICE_RECOVERING');
  const application=await normalizeBackendResponse(Response.json({error:{code:'APPLICATION_ERROR'}},{status:500}),'cold-start');
  assert.equal(application.status,500);assert.equal((await application.json()).error.code,'APPLICATION_ERROR');
});
test('source errors and successful payloads keep their own semantics', async () => {
  const response=await normalizeBackendResponse(Response.json({error:{code:'INVENTORY_NOT_LOADED'}},{status:503}),'checked');
  assert.equal((await response.json()).error.code,'INVENTORY_NOT_LOADED');
});
test('browser retries recovery only, within a fixed attempt bound', async () => {
  const originalFetch=globalThis.fetch,originalTimer=globalThis.setTimeout;let calls=0;
  globalThis.setTimeout=(fn)=>originalTimer(fn,0);
  try {
    globalThis.fetch=async()=>{calls++;return calls===1 ? Response.json({error:{code:'SERVICE_RECOVERING'}},{status:503,headers:{'retry-after':'1'}}) : Response.json({items:[1]});};
    assert.deepEqual(await fetchPublicJson('/api/test'),{items:[1]});assert.equal(calls,2);
    calls=0;globalThis.fetch=async()=>{calls++;return Response.json({error:{code:'SOURCE_UNAVAILABLE',message:'provider failure'}},{status:502});};
    await assert.rejects(fetchPublicJson('/api/test'),/SOURCE_UNAVAILABLE/);assert.equal(calls,1);
    calls=0;globalThis.fetch=async()=>{calls++;return Response.json({error:{code:'SERVICE_RECOVERING'}},{status:503});};
    await assert.rejects(fetchPublicJson('/api/test'),/SERVICE_RECOVERING/);assert.equal(calls,3);
  } finally {globalThis.fetch=originalFetch;globalThis.setTimeout=originalTimer;}
});
