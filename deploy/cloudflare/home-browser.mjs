/* Deterministic UI contracts. Fixtures exercise discovery, not source acceptance. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const web=new URL('../../src/mcp_open_data_hk/web/',import.meta.url);
const families=JSON.parse(await readFile(new URL('datasets.json',web),'utf8'));
const rows=Array.from({length:14},(_,i)=>({id:'fixture-'+i,title:`Example dataset ${String(i).padStart(2,'0')}`,titleZhHant:`示例數據 ${i}`,provider:i%2?'Example independent provider':'Example Department',providerType:i%2?'independent':'government',entryKind:'source_dataset',description:i===0?'weather <script>throw new Error("unsafe")</script>':'weather schools transport population public holidays environment economy property restaurants racing address',sourceUrl:'https://example.gov.hk/data',resourceSummary:{total:1,byStatus:{pending:1}}}));
rows[13].title='Weather observations';rows[13].titleZhHant='天氣觀測';
for(const id of ['company_registry','enigma']){const f=families.find(f=>f.id===id);rows.push({id:'mcp:'+id,packId:id,title:f.title.en,titleZhHant:f.title['zh-Hant'],description:'company',provider:id==='enigma'?'David Webb / Webb-site':'Companies Registry',providerType:id==='enigma'?'independent':'government',entryKind:'connected_service',sourceUrl:'https://example.gov.hk/company',action:{url:f.path},access:{http:[f.httpExample],tools:[f.mcpExample]}});}
const out=new URL('../../playwright-artifacts/home/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[];
try{
 for(const width of [320,390,768,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let fail=false,releaseHeld,finishHeld;const requests=[];
  const held=new Promise(resolve=>releaseHeld=resolve),heldDone=new Promise(resolve=>finishHeld=resolve);
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/catalogue/datasets?*',async route=>{
   requests.push(route.request().url());
   if(fail)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'SOURCE_UNAVAILABLE',message:'fixture failure'}})});
   const p=new URL(route.request().url()).searchParams,q=(p.get('q')||'').toLowerCase();
   if(q==='held'){await held;try{await route.fulfill({json:{items:[{...rows[0],title:'Obsolete response'}],total:1,nextOffset:null}});}catch{/* Request was cancelled by the next search. */}finally{finishHeld();}return;}
   assert.equal(p.get('order'),q?'relevance':'title');
   const items=rows.filter(d=>(!q||[d.title,d.titleZhHant,d.provider,d.description].join(' ').toLowerCase().includes(q))&&(p.get('provider')==='all'||d.providerType===p.get('provider'))&&(p.get('access')==='all'||(p.get('access')==='connected')===(d.entryKind==='connected_service'))).sort((a,b)=>(q?Number(!a.title.toLowerCase().includes(q))-Number(!b.title.toLowerCase().includes(q)):0)||a.title.toLowerCase().localeCompare(b.title.toLowerCase(),'en'));
   const offset=Number(p.get('offset')),limit=Number(p.get('limit'));
   await route.fulfill({json:{items:items.slice(offset,offset+limit),total:items.length,nextOffset:offset+limit<items.length?offset+limit:null}});
  });
  const ready=()=>page.waitForFunction(()=>!document.querySelector('#directory-catalogue').hidden&&document.querySelector('#directory-results').getAttribute('aria-busy')==='false');
  const start=()=>page.waitForFunction(()=>document.querySelector('#directory-catalogue').hidden&&document.querySelector('#directory-results').getAttribute('aria-busy')==='false');
  const search=async q=>{await page.locator('#mhk-discovery-query').fill(q);await page.locator('#mhk-discovery-query').press('Enter');await ready();};
  await page.goto(origin+'/?lang='+lang);await start();await page.waitForLoadState('networkidle');
  assert.equal(requests.length,0);assert.equal(await page.locator('.mhk-directory-row').count(),0);assert.equal(await page.locator('[data-topic-query]').count(),12);
  assert.equal(await page.locator('#directory-catalogue').isVisible(),false);
  await page.locator('[data-browse-all]').click();await ready();
  assert.equal(new URL(page.url()).searchParams.get('browse'),'all');
  await page.reload();await ready();assert.equal(await page.locator('.mhk-directory-row').count(),10);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('.mhk-directory-row summary').first().focus();await page.keyboard.press('Enter');assert.equal(await page.locator('.mhk-directory-row[open]').count(),1);
  assert.equal(await page.locator('.mhk-directory-row script').count(),0);
  const firstTitles=await page.locator('.mhk-directory-row summary strong').allTextContents();
  await page.locator('#directory-next').click();await ready();assert.equal(await page.locator('.mhk-directory-row').count(),6);
  await page.locator('#directory-previous').click();await ready();assert.deepEqual(await page.locator('.mhk-directory-row summary strong').allTextContents(),firstTitles);
  await page.locator('#directory-provider').selectOption('independent');await ready();assert.equal(new URL(page.url()).searchParams.get('provider'),'independent');
  assert.equal(await page.locator('.mhk-directory-row').count(),8);
  await page.locator('#directory-access').selectOption('connected');await ready();assert.equal(await page.locator('.mhk-directory-row').count(),1);
  const beforeReset=requests.length;await page.locator('#directory-reset').click();await start();assert.equal(requests.length,beforeReset);
  assert.equal(new URL(page.url()).searchParams.get('browse'),null);
  assert.equal(await page.locator('#mhk-discovery-query').evaluate(e=>e===document.activeElement),true);
  await search('company');assert.equal(await page.locator('.mhk-directory-row').count(),2);
  for(const summary of await page.locator('.mhk-directory-row summary').all())await summary.click();
  for(const id of ['company_registry','enigma'])assert.ok((await page.locator('#directory-results').innerText()).includes(families.find(f=>f.id===id).dates[lang]));
  const localeLink=page.locator('#directory-results a[href^="/playground"]').first();assert.equal(new URL(await localeLink.getAttribute('href'),origin).searchParams.get('lang'),lang);
  await page.locator('.mhk-language').click();await ready();assert.equal(new URL(page.url()).searchParams.get('q'),'company');assert.equal(await page.locator('.mhk-directory-row').count(),2);
  await page.locator('.mhk-language').click();await ready();
  await search('unmatched-fixture');assert.equal(await page.locator('.mhk-directory-row').count(),0);assert.ok(await page.locator('#directory-reset').isVisible());
  await page.goBack();await ready();assert.equal(await page.locator('#mhk-discovery-query').inputValue(),'company');
  fail=true;await search('weather');assert.equal(await page.locator('#directory-results [role="alert"]').count(),1);assert.equal(await page.locator('#directory-results .dataset-family').count(),families.length);
  fail=false;await page.locator('#directory-results [role="alert"] button').click();await ready();assert.equal(await page.locator('.mhk-directory-row').count(),10);
  assert.equal(await page.locator('.mhk-directory-row summary strong').first().innerText(),lang==='en'?'Weather observations':'天氣觀測');
  if(width===1280)for(const topic of await page.locator('[data-topic-query]').all()){await topic.click();await ready();assert.equal(new URL(page.url()).searchParams.get('access'),null);assert.equal(await page.locator('#directory-access').inputValue(),'all');}
  const requested=page.waitForRequest(request=>new URL(request.url()).searchParams.get('q')==='held');
  await page.locator('#mhk-discovery-query').fill('held');await page.locator('#mhk-discovery-query').press('Enter');await requested;
  assert.equal(await page.locator('.mhk-directory-row').count(),0);
  await search('weather');releaseHeld();await heldDone;assert.equal(await page.getByText('Obsolete response',{exact:true}).count(),0);
  await page.locator('#directory-reset').click();await start();await page.evaluate(()=>window.scrollTo(0,0));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:new URL(`home-${lang}-${width}.png`,out).pathname,fullPage:true});
  receipts.push({width,lang,topicFirst:true,noAutomaticCatalogueRequest:true,explicitFullCatalogue:true,relevanceSearch:true,keyboard:true,pagination:true,filters:true,languageState:true,history:true,sourceDetails:true,failureRecovery:true,obsoleteResponseIgnored:true,overflow:false});await context.close();
 }
 {
  const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage();let releaseFamily,calls=0;
  const delayed=new Promise(resolve=>releaseFamily=resolve);
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/assets/datasets.json',async route=>{await delayed;await route.fulfill({json:families});});
  await context.route('**/api/v1/catalogue/datasets?*',async route=>{calls++;assert.equal(new URL(route.request().url()).searchParams.get('order'),'relevance');await route.fulfill({json:{items:rows.filter(d=>d.entryKind==='connected_service'),total:2,nextOffset:null}});});
  try{
   const response=page.waitForResponse(r=>r.url().includes('/api/v1/catalogue/datasets?'));
   await page.goto(origin+'/?q=company&lang=en');await response;
   assert.equal(await page.locator('#directory-results').getAttribute('aria-busy'),'true');
   releaseFamily();await page.waitForFunction(()=>document.querySelector('#directory-results').getAttribute('aria-busy')==='false');
   for(const summary of await page.locator('.mhk-directory-row summary').all())await summary.click();
   for(const id of ['company_registry','enigma'])assert.ok((await page.locator('#directory-results').innerText()).includes(families.find(f=>f.id===id).dates.en));
   assert.equal(calls,1);receipts.push({width:1280,lang:'en',delayedFamilyMetadata:true,singleSearchRequest:true});
  }finally{releaseFamily();await context.close();}
 }
 for(const initial of ['provider=government','offset=10']){
  const context=await browser.newContext({viewport:{width:1280,height:900}}),page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/catalogue/datasets?*',route=>{
   const p=new URL(route.request().url()).searchParams;
   const items=rows.filter(d=>p.get('provider')==='all'||d.providerType===p.get('provider'));
   const offset=Number(p.get('offset')),limit=Number(p.get('limit'));
   return route.fulfill({json:{items:items.slice(offset,offset+limit),total:items.length,nextOffset:offset+limit<items.length?offset+limit:null}});
  });
  try{
   await page.goto(origin+'/?'+initial+'&lang=en');await page.waitForFunction(()=>!document.querySelector('#directory-catalogue').hidden&&document.querySelector('#directory-results').getAttribute('aria-busy')==='false');
   if(initial.startsWith('provider'))await page.locator('#directory-provider').selectOption('all');else await page.locator('#directory-previous').click();
   assert.equal(await page.locator('#directory-catalogue').isVisible(),true);
   await page.waitForFunction(()=>document.querySelector('#directory-results').getAttribute('aria-busy')==='false');
   assert.equal(await page.locator('.mhk-directory-row').count(),10);
   receipts.push({width:1280,lang:'en',legacyBookmark:initial,explicitBrowseIntentPreserved:true});
  }finally{await context.close();}
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipt.json',out),JSON.stringify({origin,scope:'Deterministic discovery UI fixtures; no source qualification or production deployment',receipts,errors},null,2)+'\n');console.log(JSON.stringify({cases:receipts.length,errors}));
}finally{await browser.close();}
