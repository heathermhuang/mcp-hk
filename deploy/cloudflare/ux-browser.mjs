import {openSourceExplorer} from './source-explorer-browser.mjs';
/* Real browser regressions with bounded deterministic provider responses. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const output=new URL('../../playwright-artifacts/ux/',import.meta.url);await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[];
const coverage={datasets:{discovered:2},resources:{discovered:2,byStatus:{queryable:2}}};
const dataset={id:'weather',title:'Current weather report',titleZhHant:'本港天氣報告',provider:'Hong Kong Observatory',providerType:'government',catalogue:'CSDI',sourceUrl:'https://example.gov.hk/weather',entryKind:'source_dataset'};
const resource={id:'a'.repeat(32),datasetId:'weather',url:'https://example.gov.hk/weather.json',format:'GEOJSON',catalogue:'CSDI',validation:{status:'queryable',lastValidatedAt:1792895641,lastCheckedAt:1792895641}};
const schema={recordPath:'features',fields:[{name:'geometry',types:['object']},{name:'properties',types:['object']}],queryFields:[{name:'properties.location',types:['string']},{name:'properties.rainfall',types:['number']},{name:'geometry.coordinates',types:['array']}]};
const provenance=[{sourceUrl:'https://example.gov.hk/weather',termsUrl:'https://example.gov.hk/terms',attribution:'Fixture provider',lastValidatedAt:1792895641,publicationDate:'2022-08-08',referencePeriod:null}];
const building={data:{id:'b1',name:'Fixture building',listingState:{message:null},stats:{lastUpdated:'2026-10-25'},listings:[{id:'1',title:'Sale advert',mode:'buy',priceHkd:1000000,source:'Provider',sourceUrl:null,freshness:{status:'stale',observedAt:'2026-10-01'},quality:{matchLevel:'building'}},{id:'2',title:'Rent advert',mode:'rent',priceHkd:20000,source:'Provider',sourceUrl:'https://example.com/advert',freshness:{status:'fresh',observedAt:'2026-10-25'},quality:{matchLevel:'estate'}}],listingQuality:{selection:'current',currentQualifiedCount:1,providerReturnedCount:2}}};
async function setup(){const context=await browser.newContext();const page=await context.newPage(),calls=[],sourceRequests=[];page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());await context.route(/https:\/\/apps\.sfc\.hk\//,r=>{sourceRequests.push(r.request().url());return r.abort();});
 await context.route('**/api/v1/**',async route=>{const req=route.request(),u=new URL(req.url()),path=u.pathname;calls.push({path,query:u.search,body:req.postDataJSON()});let body={},status=200;
 if(path==='/api/v1/sfc/status')body={data:{sourceId:'sfc_register',state:'unqualified',enabledModes:[],acceptedVersion:null}};
 else if(path==='/api/v1/coverage')body=coverage;
 else if(path==='/api/v1/status')body={sources:[{sourceId:'enigma',providerType:'independent',sourceUrl:'https://example.com/archive',lastSuccess:null,stale:false}]};
 else if(path==='/api/v1/catalogue/datasets'){const term=u.searchParams.get('q');if(term==='slow')await new Promise(resolve=>setTimeout(resolve,150));body={items:[{...dataset,title:term==='slow'?'Obsolete dataset':term==='fast'?'Latest dataset':dataset.title}],total:11,nextOffset:u.searchParams.get('offset')==='10'?null:10};}
 else if(path.startsWith('/api/v1/catalogue/datasets/'))body=dataset;
 else if(path==='/api/v1/resources')body={items:[resource],total:1,nextOffset:null};
 else if(path.endsWith('/schema'))body={schema,provenance,recordCount:1};
 else if(path.endsWith('/query')){assert.equal(req.postDataJSON().limit,5);assert.deepEqual(req.postDataJSON().fields,['properties.location','properties.rainfall']);body={schema,provenance,data:{items:[{'properties.location':'Central','properties.rainfall':2}]},meta:{total:1,structuredQueryable:true},warnings:[]};}
 else if(path==='/api/v1/companies/updates/status')body={data:{coverage:{latestAcceptedCoverageEnd:'2026-10-18',moneyLenderCutoff:'2026-09-30'}}};
 else if(path==='/api/v1/companies'){assert.equal(u.searchParams.get('groupBy'),'organisation');if(u.searchParams.get('view')==='latest_observed'){if(u.searchParams.get('q')==='10')body={data:{items:[{entity_id:'cr:local:00000001',name1:'Official fixture',identifier:{namespace:'cr:local:brn',value:'00000001'}}]},meta:{version:'official-'+'a'.repeat(32),groupBy:'organisation',view:'latest_observed'},provenance:[],warnings:[]};else{status=503;body={error:{code:'PACK_UNAVAILABLE',message:'Fixture official failure'}};}}else body={data:{items:[{entity_id:1,name1:'HSBC fixture',matched_fact_count:30,matched_names:[{display_name:'HSBC alias',name_kind:'former_name'}]}]},meta:{version:'fixture-v1',groupBy:'organisation',view:'archive'},provenance:[],warnings:[]};}
 else if(path==='/api/v1/companies/cr:local:00000001'||path==='/api/v1/companies/cr%3Alocal%3A00000001')body={data:{entity_id:'cr:local:00000001',name1:'Official fixture',observations:[]},meta:{version:'official-'+'a'.repeat(32),view:'latest_observed'},provenance:[],warnings:[]};
 else if(path==='/api/v1/companies/1/licences'){assert.equal(u.searchParams.get('version'),'fixture-v1');body={data:{items:[{company_id:1,registered_institution:1,activity_label:'Fixture securities',start_raw:null,start_precision:'unknown',end_raw:'2020-06-15',end_precision:'day'}]},meta:{version:'fixture-v1',nextCursor:null}};}
 else if(path==='/api/v1/companies/1')body={data:{entity_id:1,kind:'organisation',name1:'HSBC fixture',inc_raw:'1900',inc_precision:'year',dissolved_raw:null,dissolved_precision:'unknown',identifiers:[]},meta:{version:'fixture-v1'},provenance:[],warnings:[]};
 else if(path==='/api/v1/properties/search')body={data:{candidates:[{id:'b1',name:'Fixture building',district:'Southern'}]}};
 else if(path==='/api/v1/properties/building')body=building;
 else if(path==='/api/v1/properties/price-history')body={data:{buildingId:'b1',generatedAt:'2026-10-25',events:[]}};
 else if(path==='/api/v1/plates/search')body={data:{items:[],total:0,query:'AA88'},provenance:[]};
 else if(path==='/api/v1/plates/comparables')body={data:{items:[],method:'Historical fixture cohort',sampleSize:0},provenance:[]};
 else {status=503;body={error:{code:'PACK_UNAVAILABLE',message:'Fixture unavailable'}};}
 await route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
 });
 await context.route('**/downloads/companies/**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'PACK_UNAVAILABLE',message:'No fixture export'}})}));return {context,page,calls,sourceRequests};}
async function run(name,fn){const b=await setup();try{await fn(b);receipts.push({name,passed:true});}catch(e){console.error({name,errors,calls:b.calls});await b.page.screenshot({path:new URL('failure.png',output).pathname,fullPage:true});throw e;}finally{await b.context.close();}}
try{
await run('scope, pagination, history, focused detail and preview budget',async({page,calls})=>{
 await page.goto(origin+'/coverage?access=sources&lang=en');await openSourceExplorer(page);await page.locator('#datasets a').first().waitFor();await page.locator('#dataset-query').fill('weather');await page.locator('#dataset-search').evaluate(f=>f.requestSubmit());await page.waitForURL('**/coverage?**q=weather**');assert.equal(new URL(page.url()).searchParams.get('access'),'sources');
 await page.locator('#datasets-next').click();assert.equal(new URL(page.url()).searchParams.get('offset'),'10');await page.locator('#datasets-previous').click();assert.equal(new URL(page.url()).searchParams.has('offset'),false);
 await page.locator('#datasets h3 a').click();await page.locator('#resources article button').waitFor();assert.equal(await page.locator('#search-step').isVisible(),false);assert.equal(await page.locator('#resource-heading').evaluate(e=>e===document.activeElement),true);
 await page.locator('#resources article button').click();const start=calls.length;await page.getByRole('button',{name:'Show records',exact:true}).click();await page.getByRole('cell',{name:'Central',exact:true}).waitFor();assert.deepEqual(calls.slice(start).map(x=>x.path.split('/').pop()),['schema','query']);
 await page.reload();await openSourceExplorer(page);await page.locator('#preview-step').waitFor();assert.equal(await page.locator('#record-table').innerText(),'');
 await page.locator('#back-results').click();await page.goBack();await page.locator('#preview-step').waitFor();assert.equal(new URL(page.url()).searchParams.get('access'),'sources');
 await page.screenshot({path:new URL('coverage-en.png',output).pathname,fullPage:true});
});
await run('one company controller, partial source failure, grouping and focus',async({page,calls})=>{
 await page.goto(origin+'/companies?lang=en');await openSourceExplorer(page);await page.locator('#company-query').fill('HSBC');await page.locator('#company-submit').click();await page.getByRole('button',{name:'HSBC fixture',exact:true}).waitFor();assert.equal(new URL(page.url()).searchParams.get('companySource'),'both');assert.equal(calls.filter(c=>c.path==='/api/v1/companies').length,2);assert.match(await page.locator('#official-status').innerText(),/unavailable/);assert.equal(await page.locator('#official-search').count(),0);
 await page.getByRole('button',{name:'HSBC fixture',exact:true}).click();await page.locator('.company-overview-name').waitFor();assert.equal(await page.locator('#company-record-heading').evaluate(e=>e===document.activeElement),true);assert.equal(new URL(page.url()).searchParams.get('version'),'fixture-v1');
 await page.screenshot({path:new URL('companies-en.png',output).pathname,fullPage:true});
});
await run('property private text, selected URL, filter, refresh and history',async({page})=>{
 await page.goto(origin+'/properties?lang=en');await openSourceExplorer(page);await page.locator('#property-query').fill('Private search text');await page.locator('#property-search').evaluate(f=>f.requestSubmit());await page.getByRole('button',{name:/Fixture building/}).click();await page.getByRole('heading',{name:'Sale advert'}).waitFor();assert.equal(new URL(page.url()).searchParams.get('building'),'b1');assert.equal(page.url().includes('Private'),false);
 await page.locator('#property-mode').selectOption('rent');assert.equal(await page.getByRole('heading',{name:'Sale advert'}).count(),0);assert.equal(await page.getByRole('heading',{name:'Rent advert'}).count(),1);await page.reload();await openSourceExplorer(page);await page.getByRole('heading',{name:'Rent advert'}).waitFor();assert.equal(await page.locator('#property-mode').inputValue(),'rent');await page.locator('#property-history').click();await page.goBack();await page.getByRole('heading',{name:'Rent advert'}).waitFor();
});
await run('late searches cannot replace current results; official legacy URL retains identity',async({page,calls})=>{
 await page.goto(origin+'/coverage?access=sources&lang=en');await openSourceExplorer(page);await page.locator('#datasets a').first().waitFor();await page.locator('#dataset-query').fill('slow');await page.locator('#dataset-search').evaluate(f=>f.requestSubmit());await page.locator('#dataset-query').fill('fast');await page.locator('#dataset-search').evaluate(f=>f.requestSubmit());await page.getByRole('link',{name:'Latest dataset',exact:true}).waitFor();await page.waitForTimeout(200);assert.equal(await page.getByRole('link',{name:'Obsolete dataset',exact:true}).count(),0);
 const start=calls.length;await page.goto(origin+'/companies?official_q=10&official_entity=cr%3Alocal%3A00000001&official_version=official-'+ 'a'.repeat(32)+'&lang=en');await openSourceExplorer(page);await page.locator('#official-detail h3').waitFor();assert.equal(await page.locator('#company-query').inputValue(),'10');assert.equal(await page.locator('#company-results-section').isVisible(),false);assert.equal(calls.slice(start).filter(c=>c.path==='/api/v1/companies').length,1);assert.match(await page.locator('#official-detail').innerText(),/cr:local:00000001/);
});
await run('plate modes expose honoured filters and restore URL state',async({page})=>{
 await page.goto(origin+'/plates?lang=en');await openSourceExplorer(page);await page.getByRole('button',{name:'Auction history',exact:true}).click();await page.locator('#mhk-plate-form .mhk-plate-filters').waitFor();await page.getByRole('button',{name:'Similar plates',exact:true}).click();assert.equal(await page.locator('#mhk-plate-form .mhk-plate-filters').isVisible(),false);assert.equal(new URL(page.url()).searchParams.get('plateMode'),'comparables');await page.reload();await openSourceExplorer(page);await page.getByText('Historical fixture cohort').waitFor();assert.equal(await page.locator('#mhk-plate-form .mhk-plate-filters').isVisible(),false);
});
await run('all public pages, bilingual mobile/reflow, source status',async({page})=>{
 const routes=['/','/coverage','/demo','/sfc','/companies','/properties','/plates','/connect','/sources','/guides','/guides/hong-kong-open-data-api','/guides/connect-ai-to-hong-kong-data','/guides/data-sources-and-freshness','/about','/terms','/privacy','/docs'];
 for(const lang of ['en','zh-Hant'])for(const path of routes){await page.setViewportSize({width:320,height:800});await page.goto(origin+path+'?lang='+lang);await openSourceExplorer(page);await page.waitForLoadState('networkidle');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`${path} ${lang} overflows`);assert.deepEqual(await page.locator('.mhk-nav .mhk-navbutton').evaluateAll(links=>links.map(link=>new URL(link.href).pathname)),['/playground','/datasets','/connect','/guides','/sources']);}
 await page.goto(origin+'/sources?lang=zh-Hant');await openSourceExplorer(page);await page.locator('#mhk-status article').waitFor();assert.equal((await page.locator('#mhk-status').innerText()).includes('source_enigma'),false);await page.screenshot({path:new URL('sources-zh-mobile.png',output).pathname,fullPage:true});
});
await run('initial analytics choice stays in flow and sends no optional requests',async({context,page})=>{
 let optional=0;await context.route(/https:\/\/(www\.)?(google-analytics\.com|googletagmanager\.com)\//,r=>{optional++;return r.abort();});
 await context.route('https://mcp.hk/**',async route=>{const u=new URL(route.request().url());if(u.pathname.startsWith('/api/')||u.pathname.startsWith('/downloads/'))return route.fallback();if(u.pathname==='/assets/site-config.json')return route.fulfill({contentType:'application/json',body:JSON.stringify({googleAnalyticsId:'G-TEST123456'})});const response=await context.request.get(origin+u.pathname+u.search);return route.fulfill({response});});
 await page.setViewportSize({width:320,height:800});await page.goto('https://mcp.hk/?lang=en');await openSourceExplorer(page);await page.locator('#mhk-privacy-choice[open]').waitFor();assert.equal(optional,0);await page.keyboard.press('Tab');assert.equal(await page.locator('.mhk-skip-link').evaluate(e=>e===document.activeElement),true);const notice=await page.locator('#mhk-privacy-choice').boundingBox(),task=await page.locator('#mhk-discovery-form').boundingBox();assert.ok(notice.y+notice.height<=task.y);await page.getByRole('button',{name:'Reject analytics',exact:true}).click();assert.equal(optional,0);assert.equal(await page.locator('#mhk-privacy-choice').isVisible(),false);
});
await run('workbook selection uses labelled choices before reading records',async({context,page})=>{
 let queries=0;const id='a'.repeat(32);await context.route('**/api/v1/resources/'+id+'/schema',route=>{const selected=route.request().postDataJSON()?.sheet;return route.fulfill({contentType:'application/json',body:JSON.stringify(selected?{schema:{fields:[{name:'value',types:['string']}],queryFields:[]},recordCount:1,provenance:[],warnings:[]}:{selectionRequired:'sheet',sheets:['English','中文'],sheetCount:2,recordCount:null})});});
 await context.route('**/api/v1/resources/'+id+'/query',route=>{const args=route.request().postDataJSON();assert.equal(args.sheet,'中文');assert.deepEqual(args.fields,['value']);queries++;return route.fulfill({contentType:'application/json',body:JSON.stringify({data:{items:[{value:'中文紀錄'}]},schema:{fields:[{name:'value',types:['string']}]},meta:{total:1,structuredQueryable:true},provenance:[],warnings:[]})});});
 await page.goto(origin+'/coverage?access=sources&dataset=weather&resource='+id+'&lang=en');await openSourceExplorer(page);await page.locator('#preview-step').waitFor();await page.getByRole('button',{name:'Show records',exact:true}).click();await page.getByRole('combobox',{name:'Workbook sheet',exact:true}).waitFor();assert.equal(queries,0);await page.getByRole('combobox',{name:'Workbook sheet',exact:true}).selectOption('中文');await page.getByRole('cell',{name:'中文紀錄',exact:true}).waitFor();assert.equal(queries,1);
});
await run('responsive widths, zoom reflow and keyboard navigation',async({page})=>{
 for(const width of [390,768,1280])for(const path of ['/sfc','/coverage','/companies','/properties','/connect']){await page.setViewportSize({width,height:900});await page.goto(origin+path+'?lang=zh-Hant');await openSourceExplorer(page);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,path+' width '+width);}
 await page.goto(origin+'/coverage?access=sources&lang=en');await openSourceExplorer(page);await page.keyboard.press('Tab');assert.equal(await page.locator('.mhk-skip-link').evaluate(e=>e===document.activeElement),true);await page.keyboard.press('Enter');assert.equal(await page.locator('#main-content').evaluate(e=>e===document.activeElement),true);await page.setViewportSize({width:320,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
});
await run('SFC gates, both languages, keyboard and no source reads',async({page,calls,sourceRequests})=>{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const before=calls.length;await page.setViewportSize({width,height:900});await page.goto(origin+'/sfc?lang='+lang);await openSourceExplorer(page);await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('#sfc-ce').isDisabled(),true);assert.equal(await page.locator('#sfc button[disabled]').count(),1);
  assert.equal(await page.locator('a[download]').count(),0);assert.ok(calls.slice(before).every(c=>c.path==='/api/v1/sfc/status'&&c.query===''&&c.body===null));assert.equal(sourceRequests.length,0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 }
 await page.goto(origin+'/sfc?lang=en');await openSourceExplorer(page);await page.keyboard.press('Tab');await page.keyboard.press('Enter');assert.equal(await page.locator('#main-content').evaluate(e=>e===document.activeElement),true);
 await page.locator('.mhk-language').click();await page.waitForURL(u=>u.pathname==='/sfc'&&u.searchParams.get('lang')==='zh-Hant');assert.match(await page.locator('h1').innerText(),/查找牌照/);
 await page.screenshot({path:new URL('sfc-zh-Hant.png',output).pathname,fullPage:true});
});
await run('SFC archive lookup works without fresh-source activation',async({page,calls,context})=>{
 await page.goto(origin+'/sfc?lang=en');await openSourceExplorer(page);await page.locator('#sfc-archive-ce').fill('ZZZ001');await page.locator('#sfc-archive-search').evaluate(f=>f.requestSubmit());
 await page.getByRole('cell',{name:'Fixture securities',exact:true}).waitFor();assert.match(await page.locator('#sfc-archive-record').innerText(),/Registered institution/);assert.match(await page.locator('#sfc-archive-record').innerText(),/fixture-v1/);assert.match(await page.locator('#sfc-archive-record').innerText(),/Unknown/);
 const company=calls.find(x=>x.path==='/api/v1/companies');assert.ok(company);assert.equal(calls.some(x=>x.path.startsWith('/api/v1/sfc/corporations')),false);
 for(const width of [320,390,768,1280]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
 await context.route('**/api/v1/companies?**',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'PACK_UNAVAILABLE',message:'Fixture failure'}})}));
 await page.locator('#sfc-archive-ce').fill('ZZZ002');await page.locator('#sfc-archive-search').evaluate(f=>f.requestSubmit());await page.getByText(/Any prior result remains labelled/).waitFor();assert.equal(await page.getByRole('cell',{name:'Fixture securities',exact:true}).count(),1);
 await page.screenshot({path:new URL('sfc-working-archive.png',output).pathname,fullPage:true});
});
await run('SFC paginated intervals are explicitly partial and link to pinned history',async({page,context})=>{
 const items=Array.from({length:20},(_,i)=>({company_id:1,registered_institution:0,activity_label:'Page-one activity '+i,start_raw:null,start_precision:'unknown',end_raw:null,end_precision:'unknown'}));
 await context.route('**/api/v1/companies/1/licences?**',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({data:{items},meta:{version:'fixture-v1',nextCursor:'fixture-next-page'}})}));
 for(const lang of ['en','zh-Hant']){
  await page.goto(origin+'/sfc?lang='+lang);await openSourceExplorer(page);await page.locator('#sfc-archive-ce').fill('ZZZ001');await page.locator('#sfc-archive-search').evaluate(f=>f.requestSubmit());await page.locator('#sfc-archive-record tbody tr').first().waitFor();assert.equal(await page.locator('#sfc-archive-record tbody tr').count(),20);
  assert.match(await page.locator('#sfc-archive-record').innerText(),lang==='en'?/Only the first page is shown/:/只顯示第一頁/);
  const link=new URL(await page.locator('#sfc-archive-record a').getAttribute('href'),origin);assert.equal(link.searchParams.get('tab'),'licences');assert.equal(link.searchParams.get('version'),'fixture-v1');assert.equal(link.searchParams.get('entity'),'1');assert.equal(link.searchParams.get('lang'),lang);
 }
});
await run('asynchronous source status links retain locale and fragment',async({page,context})=>{
 await context.route('**/api/v1/status',r=>r.fulfill({contentType:'application/json',body:JSON.stringify({sources:[{sourceId:'sfc_archive',title:'SFC licence archive',titleZhHant:'證監會牌照歷史檔案',providerType:'independent',sourceUrl:'https://example.com/archive',availability:'checked_on_query',statusUrl:'/api/v1/sfc/status',statusPage:'/sfc#sfc-archive-heading'}]})}));
 for(const lang of ['en','zh-Hant'])for(const width of [390,1280]){
  await page.setViewportSize({width,height:900});await page.goto(origin+'/sources?lang='+lang);await openSourceExplorer(page);const link=page.locator('#mhk-status a[href*="/sfc#"],#mhk-status a[href*="/sfc?"]');await link.waitFor();
  const target=new URL(await link.getAttribute('href'),origin);assert.equal(target.pathname,'/sfc');assert.equal(target.searchParams.get('lang'),lang);assert.equal(target.hash,'#sfc-archive-heading');
  await link.click();await page.waitForURL(u=>u.pathname==='/sfc'&&u.searchParams.get('lang')===lang);assert.equal(await page.locator('html').getAttribute('lang'),lang);
 }
});
assert.deepEqual(errors,[]);console.log(JSON.stringify({browser:browser.version(),receipts,errors},null,2));await writeFile(new URL('result.json',output),JSON.stringify({browser:browser.version(),receipts,errors},null,2));
}finally{await browser.close();}
