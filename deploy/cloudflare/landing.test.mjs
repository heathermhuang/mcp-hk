import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {test} from 'node:test';
class Element {
  constructor(){this.listeners={};this.dataset={};this.children=[];this.textContent='';}
  addEventListener(event,fn){this.listeners[event]=fn;}
  setAttribute(){} removeAttribute(){} replaceChildren(){this.children=[];} append(...values){this.children.push(...values);}
  querySelectorAll(){return [];}
}
test('opening home only loads the edge overview; source status loads once on demand',async()=>{
  const originalFetch=globalThis.fetch,calls=[],elements=new Map(),sourceLink=new Element();sourceLink.dataset.screen='sources';
  const element=selector=>{if(!elements.has(selector))elements.set(selector,new Element());return elements.get(selector);};
  const root={querySelector:element,querySelectorAll:selector=>selector==='[data-screen],[data-go]'?[sourceLink]:[]};
  let resolveOverview,resolveStatus;
  const overviewRead=new Promise(resolve=>{resolveOverview=resolve;}),statusRead=new Promise(resolve=>{resolveStatus=resolve;});
  globalThis.fetch=async path=>{calls.push(path);resolveOverview();if(path==='/assets/overview.json'){resolveOverview();return Response.json({datasets:{discovered:4984},resources:{discovered:63360,byStatus:{queryable:40765}}});}if(path==='/api/v1/coverage')return Response.json({realtimeTransport:{resources:[]}});if(path==='/api/v1/status'){resolveStatus();return Response.json({sources:[]});}throw Error('Unexpected backend request: '+path);};
  try {
    const document={getElementById:()=>root,createElement:()=>new Element(),documentElement:{}},location=new URL('https://mcp.hk/');
    const context={document,location,URLSearchParams,Event,history:{pushState(){}},window:{addEventListener(){},dispatchEvent(){}},translations:{en:{provenanceLabel:'Source'}},MhkI18n:{lang:'en',locale:'en',t:key=>key,apply(){},coverageSummary(){}}};
    const url=new URL('../../src/mcp_open_data_hk/web/app.js',import.meta.url);
    vm.runInNewContext(readFileSync(url,'utf8'),context,{filename:fileURLToPath(url),importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
    await overviewRead;await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(calls,['/assets/overview.json']);
    sourceLink.listeners.click({preventDefault(){}});await statusRead;await new Promise(resolve=>setImmediate(resolve));
    sourceLink.listeners.click({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(calls,['/assets/overview.json','/api/v1/status','/api/v1/coverage']);
  } finally {globalThis.fetch=originalFetch;}
});

test('neighbourhood form submits the address API rather than the plate layout div',async()=>{
  const originalFetch=globalThis.fetch,calls=[],elements=new Map();
  const element=selector=>{if(!elements.has(selector))elements.set(selector,new Element());return elements.get(selector);};
  const root={querySelector:element,querySelectorAll:()=>[]};
  globalThis.fetch=async path=>{calls.push(path);if(path==='/assets/overview.json')return Response.json({datasets:{discovered:1},resources:{discovered:1,byStatus:{}}});if(path.startsWith('/api/v1/addresses/search?'))return Response.json({data:{items:[]}});throw Error('Unexpected request '+path);};
  try{
    const context={document:{getElementById:()=>root,createElement:()=>new Element(),documentElement:{}},location:new URL('https://mcp.hk/demo'),URLSearchParams,Event,history:{pushState(){throw Error('Form must not navigate');}},window:{addEventListener(){},dispatchEvent(){}},translations:{en:{}},MhkI18n:{lang:'en',locale:'en',t:k=>k,apply(){},coverageSummary(){}}};
    vm.runInNewContext(readFileSync(new URL('../../src/mcp_open_data_hk/web/app.js',import.meta.url),'utf8'),context,{filename:fileURLToPath(new URL('../../src/mcp_open_data_hk/web/app.js',import.meta.url)),importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
    assert.equal(typeof element('#mhk-address-form').listeners.submit,'function');assert.equal(element('.mhk-search').listeners.submit,undefined);
    element('#mhk-query').value='Central';let prevented=false;await element('#mhk-address-form').listeners.submit({preventDefault(){prevented=true;}});
    assert.equal(prevented,true);assert.equal(calls.filter(p=>p.startsWith('/api/v1/addresses/search?')).length,1);assert.match(calls.find(p=>p.startsWith('/api/v1/addresses/search?')),/q=Central/);
  }finally{globalThis.fetch=originalFetch;}
});

test('homepage search has a real catalogue fallback without JavaScript',()=>{
  const html=readFileSync(new URL('../../src/mcp_open_data_hk/web/index.html',import.meta.url),'utf8');
  assert.match(html,/<form id="mhk-discovery-form"[^>]*action="\/coverage"[^>]*method="get"/);
  assert.match(html,/<input[^>]*name="q"/);
  assert.match(html,/<input type="hidden" name="access" value="all"/);
  assert.match(html,/<input type="hidden" name="lang"[^>]*data-language-value/);
});

test('browse-all links explicitly include the full source catalogue',()=>{
  const html=readFileSync(new URL('../../src/mcp_open_data_hk/web/index.html',import.meta.url),'utf8');
  const links=[...html.matchAll(/href="([^"]+)" data-i18n="seeCoverage"/g)];
  assert.equal(links.length,2);for(const link of links)assert.equal(link[1],'/coverage?access=all');
});
