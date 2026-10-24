import assert from 'node:assert/strict';
import {test} from 'node:test';
import {boundedBytes,boundedResponse} from './response-policy.ts';
import {mcpPolicy} from './mcp-policy.ts';

test('edge method/origin policy denies unsupported methods before dispatch and preserves GET and POST',()=>{
  let dispatch=0;
  for(const method of ['PUT','PATCH','DELETE','HEAD']){
    const response=mcpPolicy(new Request('https://mcp.hk/mcp',{method}),'https://mcp.hk');if(!response)dispatch++;
    assert.equal(response.status,405);assert.equal(response.headers.get('Allow'),'GET, POST, OPTIONS');
  }
  assert.equal(dispatch,0);
  for(const method of ['GET','POST'])assert.equal(mcpPolicy(new Request('https://mcp.hk/mcp',{method}),'https://mcp.hk'),undefined);
  assert.equal(mcpPolicy(new Request('https://mcp.hk/mcp',{method:'OPTIONS'}),'https://mcp.hk').status,204);
  assert.equal(mcpPolicy(new Request('https://mcp.hk/mcp',{headers:{Origin:'https://evil.example'}}),'https://mcp.hk').status,403);
});
test('operator body reads enforce actual bytes and a whole-response deadline including stalled body',async()=>{
  assert.equal(new TextDecoder().decode(await boundedBytes(new Response('ok'),2)),'ok');
  let cancelled=0;
  const tooLarge=new ReadableStream({start(c){c.enqueue(new Uint8Array(10));},cancel(){cancelled++;}});
  await assert.rejects(boundedBytes(new Response(tooLarge),5),/RESPONSE_TOO_LARGE/);
  const stalled=new ReadableStream({pull(){return new Promise(()=>{});},cancel(){cancelled++;}});
  await assert.rejects(boundedBytes(new Response(stalled),5,10),/RESPONSE_DEADLINE/);
  assert.equal(cancelled,2);
});
test('streamed operator relay cancels overflows and stalled bodies',async()=>{
  let cancelled=0;
  const response=boundedResponse(new Response(new ReadableStream({start(c){c.enqueue(new Uint8Array(6));},cancel(){cancelled++;}})),5);
  await assert.rejects(response.arrayBuffer(),/RESPONSE_TOO_LARGE/);
  const stalled=boundedResponse(new Response(new ReadableStream({pull(){return new Promise(()=>{});},cancel(){cancelled++;}})),5,10);
  await assert.rejects(stalled.arrayBuffer(),/RESPONSE_DEADLINE/);assert.equal(cancelled,2);
});
