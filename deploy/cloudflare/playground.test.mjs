import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {validateRecipe,encodeRecipe,decodeRecipe,RequestFlow,assertFields,fieldsOf,defaultColumns,arrivalExpiry} from '../../src/mcp_open_data_hk/web/playground-state.js';
import {parseExact,exactJson,wirePresentation} from '../../src/mcp_open_data_hk/web/playground-wire.js';
import {exportPolicy,evidencePackage} from '../../src/mcp_open_data_hk/web/playground-export.js';
import {cellText} from '../../src/mcp_open_data_hk/web/playground-views.js';
import {DomainSession} from '../../src/mcp_open_data_hk/web/playground-adapters.js';
import {discoveryTarget} from './discovery.ts';
const base={v:1,family:'catalogue',lang:'en',dataset:'holiday',resource:'r1',filters:[{field:'n','kind':'integer',value:'9007199254740993'}],columns:['n']};
test('recipes restore exact intent and reject unbounded, credentialed, continuation or forged state',()=>{
 const recipe=validateRecipe(base);assert.deepEqual(decodeRecipe(encodeRecipe(recipe)),recipe);
 for(const bad of [{...base,v:2},{...base,cursor:'signed'},{...base,version:'secret'},{...base,records:[1]},{...base,filters:[...base.filters,...base.filters]},{...base,selectors:{parameters:{api_key:'secret'}}},{...base,selectors:{parameters:{Authorization:'Bearer secret'}}},{...base,selectors:{parameters:{sessionId:'private'}}},{...base,query:{source:'unknown'}},{...base,query:{meeting:'racing-results-v1-secret'}},{...base,query:{issuer:'unresolved:5'}},{...base,view:{type:'iframe'}},{...base,filters:[{field:'n',kind:'float',value:'Infinity'}]}])assert.throws(()=>validateRecipe(bad));
 for(const hash of ['#p=%XX','#x=1','#p='+('a'.repeat(8193)),'#p='+encodeURIComponent('{"__proto__":{},"v":1}')])assert.throws(()=>decodeRecipe(hash));
 assert.throws(()=>encodeRecipe({...base,filters:Array.from({length:10},(_,i)=>({field:'field'+i,kind:'string',value:'中'.repeat(1000)}))}),/TOO_LARGE/);
 assert.throws(()=>assertFields(recipe,{fields:[]}),/SAVED_FIELD_MISSING/);
 assert.equal(fieldsOf({fields:[{name:'a.b',scalarKinds:['integer']}],queryFields:[{name:'a.b',scalarKinds:['float']}]} )[0].scalarKinds[0],'integer');
 assert.deepEqual(defaultColumns({scope:'calendar_events',fields:[{name:'dtstart',types:['array']},{name:'summary',types:['string']}]}),['dtstart','summary']);
 assert.equal(cellText({kind:'json',json:'["20261001",{"value":"DATE"}]'},'en',true),'2026-10-01');
 const flow=new RequestFlow(),old=flow.start(),current=flow.start();assert.ok(old.signal.aborted&&!old.current()&&current.current());
});
test('wire codec preserves all numerical lexemes, Unicode, negative zero, collisions and missing cells',()=>{
 const raw='[{"n":9007199254740993,"f":-0.0,"d":1.23000000000000000001,"s":"001","null":null,"q":"\\\"中文","__proto__":{"safe":true}},{"n":1e+20}]';
 const tree=parseExact(raw);assert.equal(exactJson(tree),raw);assert.equal(Object.getPrototypeOf(tree[0]),null);assert.equal({}.safe,undefined);
 const p=wirePresentation(tree,['n','f','s','null','missing']);assert.equal(p.rows[0][0].text,'9007199254740993');assert.equal(p.rows[0][1].text,'-0.0');assert.equal(p.rows[0][4].kind,'missing');assert.equal(p.rows[0][3].kind,'null');
 for(const invalid of ['[1,]','{"x":1,}','{"x":01}','[true false]','"unfinished','[NaN]','0 trailing','[1'+']'.repeat(102)])assert.throws(()=>parseExact(invalid));
});
test('evidence is independently readable and hashes exact Unicode bytes, formula text, leading zeros and big numeric JSON',async()=>{
 const exact=parseExact('[{"n":9007199254740993,"name":"中文","code":"00005","formula":"=HYPERLINK(1)","none":null}]');
 const presentation=wirePresentation(exact,['n','name','code','formula','none','missing']);
 const result={rows:[{}],presentation,envelopes:[{dataset:{providerType:'government'},resource:{catalogue:'DATA.GOV.HK',validation:{status:'queryable'}},schema:{fields:[]},meta:{version:'abc'},provenance:[{termsUrl:'https://data.gov.hk/en/terms-and-conditions',attribution:'Example Department',originalResourceUrl:'https://example.gov.hk/'}]}],errors:[]};
 const recipe=validateRecipe({...base,filters:[]}),pack=await evidencePackage(result,recipe,new AbortController().signal);
 const dir=mkdtempSync(join(tmpdir(),'playground-evidence-'));try{const path=join(dir,'page.zip');writeFileSync(path,new Uint8Array(await pack.blob.arrayBuffer()));const check=spawnSync('python3',['-c',`import zipfile,json,hashlib,csv,io,sys
with zipfile.ZipFile(sys.argv[1]) as z:
 assert z.testzip() is None
 m=json.loads(z.read('manifest.json'));assert m['scope']=='displayed_page' and m['rowCount']==1
 for f in m['files']:
  data=z.read(f['file']);assert len(data)==f['bytes'] and hashlib.sha256(data).hexdigest()==f['sha256']
 rows=json.loads(z.read('records.json'));assert rows[0]['n']==9007199254740993 and rows[0]['none'] is None and 'missing' not in rows[0]
 c=list(csv.DictReader(io.StringIO(z.read('records.csv').decode('utf-8-sig'))))[0]
 assert c['n']=="'9007199254740993" and c['code']=="'00005" and c['formula'].startswith("'") and c['name']=='中文'
 assert b'terms-and-conditions' in z.read('NOTICE.txt')`,path],{encoding:'utf8'});assert.equal(check.status,0,check.stderr);}finally{rmSync(dir,{recursive:true,force:true});}
 assert.equal(exportPolicy({...result,expired:true},recipe),false);assert.equal(exportPolicy(result,{...recipe,resource:undefined,family:'seehouse'}),false);
 assert.equal(exportPolicy({...result,envelopes:[{...result.envelopes[0],dataset:{providerType:'independent'}}]},recipe),false);
});
test('Worker chooses bilingual static assets and marks query URLs noindex without rendering inputs',()=>{
 for(const lang of ['en','zh-Hant']){const canonical=discoveryTarget(new URL('https://mcp.hk/playground?lang='+lang));assert.equal(canonical.noindex,false);assert.match(canonical.asset,new RegExp('/'+lang+'/playground.html$'));const filtered=discoveryTarget(new URL('https://mcp.hk/playground?lang='+lang+'&q=private'));assert.equal(filtered.noindex,true);assert.match(filtered.asset,/-filtered.html$/);}
});
test('domain requests preserve source-specific versions/cursors, exact issuer resolution and cancellation',async()=>{
 const prior=globalThis.fetch,calls=[];let officialFail=true,issuerCalls=0;
 globalThis.fetch=async(path,options)=>{const u=new URL(path,'https://mcp.hk');calls.push({path:u.pathname,q:u.searchParams,signal:options.signal});let p;
 if(u.pathname==='/api/v1/companies'){
  if(u.searchParams.get('view')==='latest_observed'&&officialFail)return new Response(JSON.stringify({error:{code:'SOURCE_UNAVAILABLE',message:'held'}}),{status:503});
  const official=u.searchParams.get('view')==='latest_observed';p={data:{items:[{entity_id:official?'official:1':1,name1:'Same name'}]},meta:{version:official?'official-v1':'archive-v1',nextCursor:u.searchParams.has('cursor')?null:'signed-'+(official?'official':'archive')}};
 }else if(u.pathname.includes('/issuers')){issuerCalls++;p={data:{items:[{issuer_id:'webb:person:1',name:'same'},{issuer_id:'webb:person:2',name:'same'}]},meta:{version:'webb-v1',nextCursor:null}};
 }else if(u.pathname.includes('/disclosures'))p={data:{items:[{id:'d1',discloser:{name1:'Person'},event_date:'2000-01-01'}]},meta:{version:'webb-v1',nextCursor:null}};
 else throw Error('unexpected '+path);
 return new Response(JSON.stringify(p),{status:200});};
 try{const signal=new AbortController().signal,session=new DomainSession('company_registry');const first=await session.read(validateRecipe({v:1,family:'company_registry',lang:'en',query:{value:'SAME'}}),signal);assert.equal(first.errors.length,1);assert.equal(first.rows.length,1);officialFail=false;
  const count=calls.length;await session.read({query:{value:'SAME'}},signal,{retry:true});assert.equal(calls.length,count+1);assert.equal(session.current.rows.length,2);
  await session.read({query:{value:'SAME'}},signal,{next:true});const archive=calls.filter(c=>c.path==='/api/v1/companies'&&!c.q.has('view')).at(-1),official=calls.filter(c=>c.q.get('view')==='latest_observed').at(-1);assert.equal(archive.q.has('version'),false);assert.equal(archive.q.get('cursor'),'signed-archive');assert.equal(official.q.get('version'),'official-v1');
  const disclosure=new DomainSession('webb_sdi');await disclosure.read({query:{value:'5'}},signal);assert.equal(disclosure.current.rows.length,2);assert.equal(issuerCalls,1);await disclosure.read({query:{value:'5',issuer:'webb:person:2'}},signal);assert.equal(issuerCalls,1);assert.equal(calls.at(-1).q.get('issuerId'),'webb:person:2');
 }finally{globalThis.fetch=prior;}
});
test('racing profile browser/export activation and selected history cursor stay independent',async()=>{
 const original=globalThis.fetch,calls=[];let browserAllowed=false,exportAllowed=false;
 globalThis.fetch=async(path)=>{const u=new URL(path,'https://mcp.hk');calls.push(u);let p;if(u.pathname.endsWith('/status'))p={data:{profileObservations:{available:true,modes:{rest:true,browser:browserAllowed,export:exportAllowed}}}};else p={data:{items:[{sourceAnnualIndex:'25-26:1',race:{raceId:'ST:1'},fields:['Exact source field']}]},meta:{version:'racing-profile-v1-'+'a'.repeat(64),nextCursor:u.searchParams.get('cursor')?null:'signed-profile-cursor'}};return new Response(JSON.stringify(p));};
 try{const session=new DomainSession('racing'),recipe={query:{profileId:'H067',profileKind:'horse',operation:'history'}},signal=new AbortController().signal;await assert.rejects(session.read(recipe,signal),/BROWSER_NOT_ACTIVATED/);assert.equal(calls.length,1);browserAllowed=true;const first=await session.read(recipe,signal);assert.equal(first.exportUrl,null);exportAllowed=true;const next=await session.read(recipe,signal,{next:true});const exported=new URL(next.exportUrl,'https://mcp.hk');assert.equal(exported.searchParams.get('cursor'),'signed-profile-cursor');assert.equal(exported.searchParams.get('version'),'racing-profile-v1-'+'a'.repeat(64));assert.equal(next.exportKind,'profile');}finally{globalThis.fetch=original;}
});
test('official SFC history stays behind its own capability and never uses company archive endpoints',async()=>{
 const original=globalThis.fetch,calls=[];let historyAvailable=false;const version='sfc-'+'b'.repeat(32);
 globalThis.fetch=async(path)=>{const u=new URL(path,'https://mcp.hk');calls.push(u);let p;if(u.pathname==='/api/v1/sfc/status')p={data:{enabledModes:['rest','browser'],acceptedVersion:version,historyAvailable}};else if(u.pathname.endsWith('/history'))p={data:{items:[]},meta:{version,nextCursor:null}};else p={data:{ce:'AAB241',nameEn:'Exact source entity'},meta:{version}};return new Response(JSON.stringify(p));};
 try{const session=new DomainSession('sfc_archive'),signal=new AbortController().signal,recipe={query:{value:'AAB241',source:'official'}};await session.read(recipe,signal);let detail=await session.detail(session.current.actions[0],signal);assert.equal(detail.history,null);historyAvailable=true;await session.read(recipe,signal);detail=await session.detail(session.current.actions[0],signal);assert.deepEqual(detail.history.families,['history']);await session.history(detail.history,'history',null,signal);assert.equal(calls.at(-1).pathname,'/api/v1/sfc/corporations/AAB241/history');assert.equal(calls.at(-1).searchParams.get('version'),version);assert.equal(calls.some(c=>c.pathname.includes('/companies/')),false);}finally{globalThis.fetch=original;}
});

test('arrival expiry uses both provider freshness and cache deadlines and fails closed on malformed metadata',()=>{
 const envelope={schema:{transport:{operation:'arrivals',cacheTTLSeconds:20,freshUntil:105}},provenance:[{lastCheckedAt:100}]};
 assert.equal(arrivalExpiry(envelope),105000);envelope.schema.transport.freshUntil=130;assert.equal(arrivalExpiry(envelope),120000);delete envelope.schema.transport.freshUntil;assert.equal(arrivalExpiry(envelope),120000);envelope.schema.transport.freshUntil='unsafe';assert.equal(arrivalExpiry(envelope),0);assert.equal(arrivalExpiry({schema:{}}),null);
});
