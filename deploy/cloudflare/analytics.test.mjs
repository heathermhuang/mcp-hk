import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
class Element {
  constructor(tag){this.tag=tag;this.children=[];this.listeners={};this.textContent='';this.disabled=false;this.open=false;}
  append(...els){this.children.push(...els);}setAttribute(){}addEventListener(name,fn){this.listeners[name]=fn;}show(){this.open=true;this.modal=false;}showModal(){this.open=true;this.modal=true;}close(){this.open=false;this.modal=false;}
}
async function browser({stored=null,id='G-TEST123456',url='https://mcp.hk/coverage?q=private-query#secret',gpc=false,dnt=false}={}){
  let saved=stored,reloaded=false;const button=new Element('button'),body=new Element('body'),head=new Element('head'),calls=[];
  const document={body,head,cookie:'',createElement:tag=>new Element(tag),querySelectorAll:()=>[button]};
  const location=new URL(url);location.reload=()=>{reloaded=true;};
  const listeners={};
  const context=vm.createContext({document,location,navigator:{globalPrivacyControl:gpc,doNotTrack:dnt?'1':null},localStorage:{getItem:()=>saved,setItem:(k,v)=>{saved=v;}},fetch:async url=>{calls.push(url);return {ok:true,json:async()=>({googleAnalyticsId:id})};},Date,URL});
  context.window=context;context.addEventListener=(name,fn)=>{listeners[name]=fn;};context.MhkI18n={t:key=>key};
  vm.runInContext(readFileSync(new URL('../../src/mcp_open_data_hk/web/analytics.js',import.meta.url),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  const dialog=body.children[0];return {context,listeners,document,dialog,button,head,calls,reloaded:()=>reloaded,saved:()=>saved,reject:dialog.children[4],accept:dialog.children[5]};
}
test('no Google script or consent ping before choice, and rejection keeps the service usable',async()=>{
  const b=await browser();assert.equal(b.head.children.length,0);assert.equal(b.context.dataLayer,undefined);assert.deepEqual(b.calls,['/assets/site-config.json']);assert.equal(b.dialog.open,true);assert.equal(b.dialog.modal,false);
  b.reject.listeners.click();assert.equal(b.dialog.open,false);assert.equal(b.head.children.length,0);assert.equal(JSON.parse(b.saved()).allowed,false);
  b.button.listeners.click();assert.equal(b.dialog.open,true);assert.equal(b.dialog.modal,true);
});
test('affirmative consent sends sanitized page views without search, fragment or advertising consent',async()=>{
  const b=await browser();b.accept.listeners.click();assert.equal(b.head.children.length,1);assert.match(b.head.children[0].src,/googletagmanager\.com\/gtag\/js\?id=G-TEST123456/);
  const commands=b.context.dataLayer.map(args=>Array.from(args));
  const config=commands.find(args=>args[0]==='config');assert.equal(config[2].send_page_view,false);assert.equal(config[2].allow_google_signals,false);
  const event=commands.find(args=>args[0]==='event');assert.equal(event[2].page_location,'https://mcp.hk/coverage');assert.equal(event[2].page_referrer,'');
  assert.doesNotMatch(JSON.stringify(commands),/private-query|secret/);assert.equal(commands[1][2].ad_user_data,'denied');
  b.document.cookie='_ga=old; _ga_TEST123456=old';b.reject.listeners.click();assert.equal(b.context['ga-disable-G-TEST123456'],true);assert.equal(b.reloaded(),true);assert.match(b.document.cookie,/Max-Age=0/);
});
test('saved consent, expiration, browser opt-out, disabled config and previews are enforced',async()=>{
  const saved=JSON.stringify({version:1,allowed:true,at:Date.now()});
  assert.equal((await browser({stored:saved})).head.children.length,1);
  for(const options of [{stored:saved,gpc:true},{stored:saved,dnt:true},{id:''},{url:'http://127.0.0.1:8765/'},{url:'https://mcp-hk.measurable.workers.dev/'}]){
    const b=await browser(options);assert.equal(b.head.children.length,0);assert.equal(b.accept.disabled,true);
  }
  const expired=await browser({stored:JSON.stringify({version:1,allowed:true,at:Date.now()-181*86400000})});assert.equal(expired.head.children.length,0);assert.equal(expired.dialog.open,true);
});

test('in-app navigation is counted once per path and never includes queries',async()=>{
  const b=await browser();b.accept.listeners.click();
  b.context.location.pathname='/connect';b.context.location.search='?token=private';b.listeners['mhk:navigate']();b.listeners.popstate();
  const events=b.context.dataLayer.map(args=>Array.from(args)).filter(args=>args[0]==='event');
  assert.equal(events.length,2);assert.equal(events[1][2].page_location,'https://mcp.hk/connect');assert.doesNotMatch(JSON.stringify(events),/token|private/);
});

test('opening settings promotes an existing notice to an explicit modal without enabling analytics',async()=>{
 const b=await browser();assert.equal(b.dialog.modal,false);b.button.listeners.click();
 assert.equal(b.dialog.open,true);assert.equal(b.dialog.modal,true);assert.equal(b.head.children.length,0);
});
