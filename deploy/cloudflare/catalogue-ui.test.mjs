import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
class Element {
  constructor(tag='div'){this.tag=tag;this.children=[];this.listeners={};this.dataset={};this.attrs={};this.value='';this.textContent='';this.hidden=false;}
  append(...els){this.children.push(...els);}replaceChildren(...els){this.children=[...els];this.textContent='';}setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,fn){this.listeners[k]=fn;}focus(){}scrollIntoView(){}
  querySelectorAll(selector){const values=this.children.flatMap(c=>c instanceof Element?[c,...c.querySelectorAll(selector)]:[]);return values.filter(c=>selector==='button'?c.tag==='button':selector==='a'?c.tag==='a':selector==='select'?c.tag==='select':selector==='[data-source-parameter]'?'sourceParameter'in c.dataset:false);}
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function browser(){
  const ids=new Map(),el=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);},listeners={},location=new URL('https://mcp.hk/coverage?access=all&lang=en');
  const modes=['all','connected','sources'].map(access=>{const b=new Element('button');b.dataset.access=access;return b;});
  const defaults={recordPath:'',sheet:'',layer:'',parameters:'{}',filters:'{}',fields:''},form=el('record-query');form.elements=Object.fromEntries(Object.keys(defaults).map(k=>[k,new Element('input')]));
  form.reset=()=>{for(const [k,v]of Object.entries(defaults))form.elements[k].value=v;};form.reset();
  const queryButton=new Element('button');form.querySelectorAll=selector=>selector==='button'?[queryButton]:[];
  const a={id:'alpha',title:'Alpha',provider:'Provider',providerType:'government',catalogue:'DATA.GOV.HK',sourceUrl:'https://example.gov.hk/alpha'},b={...a,id:'beta',title:'Beta'};
  const first={id:'a'.repeat(32),datasetId:'alpha',format:'JSON',url:'https://example.gov.hk/a',catalogue:'DATA.GOV.HK',validation:{status:'needs_selection'},transport:{operation:'arrivals',operator:'MTR',requiredParameters:['line','sta'],parameterExamples:{line:'TWL',sta:'CEN'},cacheTTLSeconds:10}};
  const second={...first,id:'b'.repeat(32),transport:undefined},third={...second,id:'c'.repeat(32),datasetId:'beta'};
  let pendingResolve;
  const api=async(path,body)=>{
    const u=new URL(path,location);
    if(u.pathname==='/api/v1/coverage')return {datasets:{discovered:2},resources:{discovered:3,byStatus:{}}};
    if(u.pathname==='/api/v1/catalogue/datasets')return {items:u.searchParams.get('q')==='Beta'?[b]:[a,b],total:u.searchParams.get('q')==='Beta'?1:2,nextOffset:null};
    if(u.pathname.startsWith('/api/v1/catalogue/datasets/'))return u.pathname.endsWith('alpha')?a:b;
    if(u.pathname==='/api/v1/resources')return {items:u.searchParams.get('datasetId')==='beta'?[third]:[first,second],total:2,nextOffset:null};
    if(u.pathname.endsWith('/schema'))return {schema:{fields:[{name:'row',types:['string']}],queryFields:[]},recordCount:1};
    if(u.pathname.endsWith('/query'))return new Promise(resolve=>{pendingResolve=resolve;});
    throw Error('Unexpected request '+path);
  };
  const document={getElementById:el,querySelectorAll:s=>s==='[data-access]'?modes:[],createElement:t=>new Element(t),createTextNode:t=>t,title:''};
  const context=vm.createContext({document,location,URL,URLSearchParams,history:{pushState(a,b,path){location.href=new URL(path,location).href;},replaceState(a,b,path){location.href=new URL(path,location).href;}},fetchPublicJson:api,setTimeout,clearTimeout,FormData:class{constructor(f){this.f=f;}get(k){return this.f.elements[k]?.value||'';}},MhkI18n:{lang:'en',locale:'en',t:(key)=>key,apply(){},coverageSummary(){}}});
  context.window=context;context.matchMedia=()=>({matches:true});context.addEventListener=(name,fn)=>{listeners[name]=fn;};
  vm.runInContext(readFileSync(new URL('../../src/mcp_open_data_hk/web/coverage.js',import.meta.url),'utf8').replace(/^import .*\n/,''),context);
  await flush();await flush();
  const button=(id,text)=>el(id).querySelectorAll(id==='datasets'?'a':'button').find(b=>b.textContent===text);
  return {el,button,form,queryButton,listeners,location,first,second,resolve:value=>pendingResolve(value)};
}
test('switching resources clears incompatible source settings and selection state',async()=>{
  const b=await browser();b.button('datasets','Alpha').listeners.click({preventDefault(){}});await flush();
  b.button('resources','alpha · JSON').listeners.click({preventDefault(){}});
  for(const f of ['sheet','recordPath','filters','fields','parameters'])b.form.elements[f].value='old-source-value';
  b.el('resources').querySelectorAll('button')[1].listeners.click({preventDefault(){}});
  assert.equal(b.form.elements.sheet.value,'');assert.equal(b.form.elements.recordPath.value,'');assert.equal(b.form.elements.filters.value,'{}');assert.equal(b.form.elements.parameters.value,'{}');
  assert.equal(b.el('source-inputs').querySelectorAll('[data-source-parameter]').length,0);
  assert.equal(b.location.searchParams.get('resource'),b.second.id);
});
test('an old query cannot restore unrelated records after a new search',async()=>{
  const b=await browser();b.button('datasets','Alpha').listeners.click({preventDefault(){}});await flush();b.el('resources').querySelectorAll('button')[1].listeners.click({preventDefault(){}});
  b.form.listeners.submit({preventDefault(){},submitter:{value:'query'}});await flush();
  b.el('dataset-query').value='Beta';b.el('dataset-search').listeners.submit({preventDefault(){}});await flush();
  b.resolve({data:{items:[{row:'old response'}]},schema:{fields:[]},meta:{total:1,structuredQueryable:true},warnings:[],provenance:[]});await flush();await flush();
  assert.equal(b.el('preview-step').hidden,true);assert.equal(b.el('resource-step').hidden,true);assert.equal(b.el('record-table').children.length,0);assert.equal(b.queryButton.disabled,true);
  assert.equal(b.location.searchParams.get('q'),'Beta');assert.equal(b.location.searchParams.has('resource'),false);
});
test('back/refresh URL state restores the selected dataset and source',async()=>{
  const b=await browser();b.button('datasets','Alpha').listeners.click({preventDefault(){}});await flush();b.el('resources').querySelectorAll('button')[1].listeners.click({preventDefault(){}});const saved=b.location.href;
  b.button('datasets','Beta').listeners.click({preventDefault(){}});await flush();assert.equal(b.location.searchParams.has('resource'),false);
  b.location.href=saved;await b.listeners.popstate();await flush();
  assert.equal(b.el('preview-step').hidden,false);assert.equal(b.location.searchParams.get('dataset'),'alpha');assert.equal(b.location.searchParams.get('resource'),b.second.id);
});
test('replacement query loading and malformed objects never retain prior response JSON',async()=>{
  const b=await browser();b.button('datasets','Alpha').listeners.click({preventDefault(){}});await flush();b.el('resources').querySelectorAll('button')[1].listeners.click({preventDefault(){}});
  b.form.listeners.submit({preventDefault(){},submitter:{value:'query'}});await flush();
  b.resolve({data:{items:[{row:'old response'}]},schema:{fields:[]},meta:{total:1,structuredQueryable:true},warnings:[],provenance:[]});await flush();await flush();
  assert.match(b.el('record-response').textContent,/old response/);
  b.form.listeners.submit({preventDefault(){},submitter:{value:'query'}});
  assert.equal(b.el('record-response').textContent,'');
  b.resolve({data:{items:[]},schema:{fields:[]},meta:{total:0,structuredQueryable:true},warnings:[],provenance:[]});await flush();await flush();
  for(const value of ['{','null','[]','"text"']){
    b.form.elements.parameters.value=value;b.form.listeners.submit({preventDefault(){},submitter:{value:'query'}});await flush();
    assert.equal(b.el('record-response').textContent,'');assert.equal(b.el('record-table').children.some(e=>e.tag==='table'),false);assert.equal(b.el('query-message').textContent,'sourceError');assert.equal(b.queryButton.disabled,false);
  }
});
test('resource directory status, format, page and selection survive URL restoration',async()=>{
  const b=await browser();b.el('coverage-status').value='queryable';b.el('directory').listeners.click({preventDefault(){}});await flush();
  b.el('resource-format').value='JSON';b.el('resource-format').listeners.change();await flush();
  b.el('resources-next').listeners.click({target:{dataset:{offset:'15'}}});await flush();
  b.el('resources').querySelectorAll('button')[1].listeners.click({preventDefault(){}});const saved=b.location.href;
  assert.equal(b.location.searchParams.get('directory'),'1');assert.equal(b.location.searchParams.get('status'),'queryable');
  b.el('dataset-query').value='Beta';b.el('dataset-search').listeners.submit({preventDefault(){}});await flush();
  b.el('coverage-status').value='unavailable';b.location.href=saved;await b.listeners.popstate();await flush();
  assert.equal(b.el('resource-step').hidden,false);assert.equal(b.el('coverage-status').value,'queryable');assert.equal(b.el('resource-format').value,'JSON');
  assert.equal(b.location.searchParams.get('sourceOffset'),'15');assert.equal(b.location.searchParams.get('resource'),b.second.id);assert.equal(b.el('preview-step').hidden,false);
});
