import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
const source=readFileSync(new URL('../../src/mcp_open_data_hk/web/webmcp.js',import.meta.url),'utf8');
function setup({fallback=false,present=true,response=()=>Response.json({data:[{id:'source-record'}],provenance:[{sourceUrl:'https://data.gov.hk/'}],warnings:['reference-period']})}={}) {
  const tools=[],calls=[],warnings=[],events={};
  const api={registerTool(tool){tools.push(tool);return Promise.resolve();}};
  const context={document:fallback?{}:{modelContext:present?api:undefined},navigator:fallback?{modelContext:api}:{},window:{addEventListener:(name,fn)=>{events[name]=fn;}},fetch:async(...args)=>{calls.push(args);return response();},AbortController,AbortSignal,URLSearchParams,TextDecoder,Uint8Array,Promise,console:{warn:x=>warnings.push(x)}};
  vm.runInNewContext(source,context);return {tools,calls,warnings,events};
}
test('WebMCP tools are optional, read-only and support the documented legacy API',()=>{
  assert.equal(setup({present:false}).tools.length,0);
  for(const fallback of [false,true]) {
    const b=setup({fallback});assert.equal(b.tools.length,2);
    for(const tool of b.tools){assert.equal(tool.annotations.readOnlyHint,true);assert.equal(tool.annotations.destructiveHint,false);}
  }
});
test('catalogue tool reads a fixed first-party API and preserves source provenance and warnings',async()=>{
  const b=setup(),result=await b.tools[0].execute({q:'public holidays',limit:3,access:'all'});
  assert.equal(b.calls[0][0],'/api/v1/catalogue/datasets?q=public+holidays&access=all&limit=3');
  assert.equal(b.calls[0][1].credentials,'omit');assert.equal(b.calls[0][1].redirect,'error');
  assert.deepEqual(JSON.parse(result.content[0].text),{data:[{id:'source-record'}],provenance:[{sourceUrl:'https://data.gov.hk/'}],warnings:['reference-period']});
  await b.tools[1].execute({});assert.equal(b.calls[1][0],'/api/v1/packs');
});
test('invalid input, arbitrary URLs and provider failures cannot become successful empty results',async()=>{
  const b=setup();
  for(const input of [{q:''},{q:'a'.repeat(201)},{q:'weather',limit:11},{q:'weather',access:'secret'},{q:'weather',url:'https://elsewhere.test'},null]) await assert.rejects(()=>b.tools[0].execute(input));
  await assert.rejects(()=>b.tools[1].execute({token:'private'}));assert.equal(b.calls.length,0);
  const failed=setup({response:()=>new Response('unavailable',{status:503})});
  await assert.rejects(()=>failed.tools[0].execute({q:'weather'}),/HTTP 503/);
  const oversized=setup({response:()=>new Response('x'.repeat(2*1024*1024+1))});
  await assert.rejects(()=>oversized.tools[1].execute({}),/exceeded/);
});
