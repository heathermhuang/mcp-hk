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
  globalThis.fetch=async path=>{calls.push(path);resolveOverview();if(path==='/assets/overview.json'){resolveOverview();return Response.json({datasets:{discovered:4984},resources:{discovered:63360,byStatus:{queryable:40765}}});}if(path==='/api/v1/status'){resolveStatus();return Response.json({sources:[]});}throw Error('Unexpected backend request: '+path);};
  try {
    const document={getElementById:()=>root,createElement:()=>new Element(),documentElement:{}},location=new URL('https://mcp.hk/');
    const context={document,location,URLSearchParams,history:{pushState(){}},window:{addEventListener(){}},translations:{en:{provenanceLabel:'Source'}},MhkI18n:{lang:'en',locale:'en',t:key=>key,apply(){},coverageSummary(){}}};
    const url=new URL('../../src/mcp_open_data_hk/web/app.js',import.meta.url);
    vm.runInNewContext(readFileSync(url,'utf8'),context,{filename:fileURLToPath(url),importModuleDynamically:vm.constants.USE_MAIN_CONTEXT_DEFAULT_LOADER});
    await overviewRead;await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(calls,['/assets/overview.json']);
    sourceLink.listeners.click({preventDefault(){}});await statusRead;await new Promise(resolve=>setImmediate(resolve));
    sourceLink.listeners.click({preventDefault(){}});await new Promise(resolve=>setImmediate(resolve));assert.deepEqual(calls,['/assets/overview.json','/api/v1/status']);
  } finally {globalThis.fetch=originalFetch;}
});
