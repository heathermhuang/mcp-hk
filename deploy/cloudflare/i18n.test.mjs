import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
const web = new URL('../../src/mcp_open_data_hk/web/',import.meta.url);
const read = name => readFileSync(new URL(name,web),'utf8');
class Element {
  constructor(attrs={}) {this.attrs={...attrs};this.dataset={};this.children=[];this.listeners={};this.textContent='';}
  getAttribute(name) {return this.attrs[name] ?? null;}
  setAttribute(name,value) {this.attrs[name]=value;}
  removeAttribute(name) {delete this.attrs[name];}
  addEventListener(name,fn) {this.listeners[name]=fn;}
  append(...nodes) {this.children.push(...nodes);}
  replaceChildren(...nodes) {this.children=[...nodes];this.textContent='';}
}
function browser(url='https://mcp.hk/',saved=null,denied=false) {
  let stored=saved;
  const label=new Element();label.dataset.i18n='navData';
  const placeholder=new Element({'data-i18n-placeholder':'datasetPlaceholder'}),button=new Element();
  const link=new Element({href:'/coverage?q=weather#results'}),external=new Element({href:'https://data.gov.hk/en/'}),api=new Element({href:'/api/v1/coverage'});
  const nav=['/','/coverage','/connect','/sources'].map(href=>new Element({href}));
  const location=new URL(url),events=[];
  const document={documentElement:{},createElement:()=>new Element(),querySelectorAll:selector=>({'.mhk-navbutton':nav,'[data-i18n]':[label],'[data-i18n-placeholder]':[placeholder],'.mhk-language':[button],'a[href]':[link,external,api]}[selector] || [])};
  const context=vm.createContext({document,location,URL,Event,history:{replaceState:(_a,_b,value)=>{location.href=new URL(value,location.href).href;}},localStorage:{getItem(){if(denied)throw Error('denied');return stored;},setItem(_key,value){if(denied)throw Error('denied');stored=value;}},addEventListener(){},dispatchEvent:event=>events.push(event.type)});
  context.window=context;vm.runInContext(read('translations.js')+'\n'+read('i18n.js'),context);
  return {context,document,label,placeholder,button,link,external,api,location,events,nav,stored:()=>stored};
}
test('language selection updates UI, accessible labels, URL and persistent navigation',()=>{
  const b=browser();b.button.listeners.click();
  assert.equal(b.document.documentElement.lang,'zh-Hant');assert.equal(b.label.textContent,'瀏覽數據');
  assert.match(b.placeholder.attrs.placeholder,/天氣/);assert.equal(b.button.attrs['aria-label'],'Switch to English');
  assert.equal(b.stored(),'zh');assert.equal(b.location.search,'?lang=zh-Hant');
  assert.equal(b.link.attrs.href,'/coverage?q=weather&lang=zh-Hant#results');
  assert.equal(b.external.attrs.href,'https://data.gov.hk/en/');assert.equal(b.api.attrs.href,'/api/v1/coverage');assert.deepEqual(b.events,['mhk:language']);
});
test('saved locale survives pages; explicit links override it and storage denial still works',()=>{
  assert.equal(browser('https://mcp.hk/connect','zh').label.textContent,'瀏覽數據');assert.equal(browser('https://mcp.hk/?lang=en','zh').label.textContent,'Browse data');
  const b=browser('https://mcp.hk/coverage?lang=zh-Hant',null,true);b.button.listeners.click();assert.equal(b.label.textContent,'Browse data');assert.equal(b.location.search,'?lang=en');
});
test('landing and explorer have complete dictionaries and shared language controls',()=>{
  const b=browser(),dictionary=vm.runInContext('translations',b.context);assert.deepEqual(Object.keys(dictionary.en).sort(),Object.keys(dictionary.zh).sort());
  for(const file of ['index.html','coverage.html']) {
    const html=read(file);assert.match(html,/assets\/i18n\.js/);assert.match(html,/mhk-language/);
    for(const m of html.matchAll(/data-i18n(?:-html|-placeholder|-aria-label|-content)?="([^"]+)"/g)) for(const lang of ['en','zh']) assert.ok(dictionary[lang][m[1]],`${file}: missing ${lang}.${m[1]}`);
    assert.doesNotMatch(html,/Three government packs|Three data packs|計劃中的遠端|INTERACTIVE CONCEPT|NO LIVE DATA/);
  }
});
test('coverage metrics use supplied counts and retain the incomplete-coverage qualification',()=>{
  const b=browser('https://mcp.hk/?lang=zh-Hant'),box=new Element();
  b.context.MhkI18n.coverageSummary(box,{asOf:'2026-10-16T23:11:28Z',datasets:{discovered:4984},resources:{discovered:63360,byStatus:{queryable:40765}}});
  assert.deepEqual(box.children[0].children.map(p=>p.children[0].textContent),['4,984','63,360','40,765']);assert.match(box.children[1].textContent,/部分仍未能查詢/);assert.match(box.children[2].textContent,/數字更新時間.*2026/);
  b.context.MhkI18n.coverageSummary(box,null,true);assert.match(box.textContent,/暫時無法/);
});
test('translated form labels never replace their nested inputs',()=>{
  for(const file of ['index.html','coverage.html']) for(const match of read(file).matchAll(/<label([^>]*)>([\s\S]*?)<\/label>/g)) {
    if (/\bdata-i18n="/.test(match[1])) assert.doesNotMatch(match[2],/<(?:input|textarea|select)\b/);
  }
});

test('static translation does not overwrite generated HTTP/MCP request examples',()=>{
  assert.doesNotMatch(read('coverage.html'), /<pre[^>]*\bdata-i18n=/);
});

test('primary routes have one active item and examples are outside primary navigation',()=>{
  for(const path of ['/','/coverage','/demo','/plates','/connect','/sources','/data']) for(const lang of ['en','zh-Hant']) {
    const b=browser('https://mcp.hk'+path+'?lang='+lang);
    const expected=['/demo','/plates'].includes(path)?[]:[path==='/data'?'/coverage':path];
    assert.deepEqual(b.nav.filter(link=>link.attrs['aria-current']==='page').map(link=>link.attrs.href),expected);
    b.button.listeners.click();
    assert.equal(b.nav.filter(link=>link.attrs['aria-current']==='page').length,expected.length);
  }
});
test('data browser shares the same complete navigation and footer as the other pages',()=>{
  const shell=(file,tag)=>read(file).match(new RegExp('<'+tag+' class="mhk-'+(tag==='header'?'nav':'foot')+'">[\\s\\S]*?</'+tag+'>'))[0];
  assert.equal(shell('index.html','header'),shell('coverage.html','header'));
  assert.equal(shell('index.html','footer'),shell('coverage.html','footer'));
  const links=[...shell('coverage.html','header').matchAll(/class="mhk-navbutton"[^>]*href="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(links,['/','/coverage','/connect','/sources']);
  const examples=read('index.html').match(/<div class="mhk-packs mhk-demos">([\s\S]*?)<\/div>/)[1];
  for(const path of ['/demo','/plates']) assert.ok(examples.includes('href="'+path+'"'),path+' remains accessible as a homepage example');
});
