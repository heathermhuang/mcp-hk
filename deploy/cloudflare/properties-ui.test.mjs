import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const flush=()=>new Promise(resolve=>setImmediate(resolve));
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.attrs={};this.value='';this.hidden=false;this.textContent='';}
  setAttribute(name,value){this.attrs[name]=value;}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=[...items];}
  addEventListener(name,fn){this.listeners[name]=fn;}
}
test('expired advert links remain disabled and listing qualification is visible',async()=>{
  const els=new Map();const el=id=>{if(!els.has(id))els.set(id,new Element());return els.get(id);};
  el('property-query').value='Kwun Chiu Court';el('property-quality').value='current';
  const requests=[];
  const expired={id:'28hse:expired',source:'28hse',title:'Expired advert',mode:'buy',priceHkd:1000000,saleableAreaFt2:300,sourceUrl:null,sourceAttribution:{url:'https://historical.example/expired'},freshness:{status:'stale',observedAt:'2026-10-01'},quality:{matchLevel:'estate'}};
  const live={...expired,id:'current',title:'Current advert',sourceUrl:'https://source.example/current',quality:{matchLevel:'building'}};
  const fetchPublicJson=async path=>{requests.push(path);return path.includes('/search')?{data:{candidates:[{id:'b1',name:'Building',district:'Southern'}]}}:{data:{id:'b1',name:'Building',listingState:{message:null},stats:{lastUpdated:null},listings:[expired,live],listingQuality:{selection:'current',currentQualifiedCount:1,providerReturnedCount:2}}};};
  const context=vm.createContext({document:{getElementById:el,createElement:t=>new Element(t)},URL,URLSearchParams,AbortController,location:new URL('https://mcp.hk/properties'),history:{state:null,pushState(){},replaceState(){}},MhkI18n:{locale:'en',t:key=>key,date:x=>x},fetchPublicJson});context.window=context;context.addEventListener=()=>{};
  vm.runInContext(readFileSync(new URL('../../src/mcp_open_data_hk/web/properties.js',import.meta.url),'utf8').replace(/^import .*\n/,''),context);
  el('property-search').listeners.submit({preventDefault(){}});await flush();
  const candidate=el('property-candidates').children[0];
  candidate.listeners.click();
  assert.equal(el('property-candidates').children[0],candidate,'loading must retain the activated node');
  assert.equal(candidate.attrs['aria-pressed'],'true');
  await flush();
  assert.equal(el('property-candidates').children[0],candidate,'results must retain the activated node');
  assert.match(requests[1],/quality=current/);
  const cards=el('property-records').children;
  assert.equal(cards.length,2);
  assert.equal(cards[0].children.filter(x=>x.tagName==='a').length,0);
  assert.equal(cards[1].children.filter(x=>x.tagName==='a').length,1);
  assert.ok(cards[0].children.some(x=>x.textContent==='propertySourceUnavailable'));
  assert.ok(cards[0].children.some(x=>x.textContent==='propertyEstateMatch'));
});
