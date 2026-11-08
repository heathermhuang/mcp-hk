/* Rendered operator fixtures; no provider qualification or independent-user claim. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const out=new URL('../../playwright-artifacts/search-record/',import.meta.url);await mkdir(out,{recursive:true});
const receipts=[],errors=[];
try{
 for(const width of [320,390,768,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let generation='a',held=false,malicious=false;const bodies=[];
  const dataset={id:'fixture',title:'School source rows',titleZhHant:'學校來源紀錄',provider:'Education Department',providerType:'government',entryKind:'source_dataset',sourceUrl:'https://example.gov.hk/school',resourceSummary:{total:16,byStatus:{needs_selection:16}}};
  const resource={id:'file',datasetId:'fixture',format:'XLSX',url:'https://example.gov.hk/files',catalogue:'DATA.GOV.HK',aliases:[{name:'School source'}],validation:{status:'needs_selection'}};
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/**',async route=>{
   const req=route.request(),u=new URL(req.url()),path=u.pathname,reply=json=>route.fulfill({json});
   if(path==='/api/v1/coverage')return reply({datasets:{discovered:1},resources:{discovered:16,byStatus:{needs_selection:16}}});
   if(path==='/api/v1/catalogue/datasets')return reply({items:[dataset],generation,total:21,nextOffset:10});
   if(path==='/api/v1/catalogue/datasets/fixture')return reply(dataset);
   if(path==='/api/v1/resources')return reply({items:[resource],total:16,nextOffset:15,generation});
   if(path==='/api/v1/resources/file')return reply(resource);
   if(path.endsWith('/schema')||path.endsWith('/query')){
    const body=req.postDataJSON();bodies.push(body);
    if(held)return route.fulfill({status:422,json:{error:{code:'SOURCE_ACCESS_HOLD',message:'Source remains held'}}});
    const field=!body.recordPath?'recordPath':!body.sheet?'sheet':null;
    if(field){const value=field==='recordPath'?'reports/2026.xlsx':'2026',option={value,label:value,nextAction:{tool:malicious?'hk_catalogue_search':'hk_resource_schema',arguments:{resourceId:'file',[field]:value,parameters:{date:'2026-11-08'},...(field==='sheet'?{recordPath:'reports/2026.xlsx'}:{})}}};
     return reply({resource,selectionRequired:field==='recordPath'?'recordPath':'sheet',selections:[{argument:field,options:[option],scopedToParameterNames:['date'],...(field==='sheet'?{scopedToRecordPath:'reports/2026.xlsx'}:{})}]});}
    assert.equal(body.recordPath,'reports/2026.xlsx');assert.equal(body.sheet,'2026');assert.deepEqual(body.parameters,{date:'2026-11-08'});
    return reply({resource,schema:{fields:[{name:'name',types:['string']}]},data:{items:[{name:'Published school session row'}]},meta:{total:1,nextOffset:null,structuredQueryable:true},warnings:[],provenance:[{sourceUrl:resource.url,attribution:'Official school source',retrievedAt:1794103200,referencePeriod:'2026'}]});
   }
   return route.fulfill({status:404,json:{error:{code:'NOT_FOUND',message:'fixture'}}});
  });
  const ready=()=>page.waitForFunction(()=>document.querySelector('#directory-results')?.getAttribute('aria-busy')==='false');
  await page.goto(origin+'/?q=all&access=sources&provider=government&lang='+lang);await ready();await page.locator('#mhk-discovery-query').press('Enter');await ready();assert.equal(new URL(page.url()).searchParams.get('q'),'all');
  await page.locator('.mhk-directory-row summary').click();
  const a=page.locator('.mhk-directory-detail a[href^="/coverage"]').first(),u=new URL(await a.getAttribute('href'),origin);
  for(const [k,v]of Object.entries({q:'all',access:'sources',provider:'government',dataset:'fixture',lang}))assert.equal(u.searchParams.get(k),v);
  await a.click();await page.locator('#resources button').first().waitFor({state:'attached'});await page.locator('#resources details').evaluateAll(es=>es.forEach(e=>e.open=true));assert.equal(await page.locator('#dataset-query').inputValue(),'all');
  await page.locator('#resources button').first().click();
  await page.locator('#query-options').evaluate(e=>e.open=true);await page.locator('[name="parameters"]').fill('{"date":"2026-11-08"}');
  await page.locator('button[value="query"]').click();await page.locator('#record-path-choices select').waitFor();
  await page.locator('#record-path-choices select').selectOption('0');
  await page.waitForFunction(()=>document.querySelector('#record-path-choices')?.textContent.includes('2026')&&document.querySelector('[name="recordPath"]').value==='reports/2026.xlsx');
  await page.locator('#record-path-choices select').selectOption('0');await page.locator('#record-table tbody tr').waitFor();
  assert.match(await page.locator('#resource-citations').innerText(),/Official school source/);
  assert.equal(new URL(page.url()).searchParams.get('recordPath'),'reports/2026.xlsx');assert.equal(new URL(page.url()).searchParams.get('sheet'),'2026');
  await page.reload();await page.locator('#preview-step:not([hidden])').waitFor();
  assert.equal(await page.locator('[name="recordPath"]').inputValue(),'reports/2026.xlsx');assert.equal(await page.locator('[name="sheet"]').inputValue(),'2026');
  await page.locator('.mhk-language').click();await page.locator('button[value="query"]').click();await page.locator('#record-table tbody tr').waitFor();
  assert.equal(new URL(page.url()).searchParams.get('q'),'all');assert.equal(new URL(page.url()).searchParams.get('provider'),'government');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:new URL(`${lang}-${width}.png`,out).pathname,fullPage:true});
  held=true;await page.locator('button[value="query"]').click();await page.waitForFunction(()=>document.querySelector('#record-response').textContent==='');assert.equal(await page.locator('#record-table tbody tr').count(),0);
  held=false;malicious=true;await page.locator('#query-options').evaluate(e=>e.open=true);await page.locator('[name="sheet"]').fill('');await page.locator('[name="recordPath"]').fill('');await page.locator('button[value="query"]').click();
  await page.waitForFunction(()=>document.querySelector('#record-response').textContent.includes('hk_catalogue_search'));assert.equal(await page.locator('#record-path-choices select').count(),0);
  await page.goto(origin+'/?q=school&lang='+lang);await ready();generation='b';await page.locator('#directory-next').click();await ready();
  await page.waitForFunction(()=>!new URL(location.href).searchParams.has('offset'));assert.match(await page.locator('#directory-results').innerText(),lang==='en'?/catalogue changed/:/目錄已更新/);
  // The selected dataset is restored by identity even when the search page differs.
  await page.goto(origin+'/coverage?q=unmatched&dataset=fixture&resource=file&lang='+lang);await page.locator('#preview-step:not([hidden])').waitFor();
  assert.match(await page.locator('#selected-resource').innerText(),/School/);
  receipts.push({width,lang,literalAll:true,filters:true,typedFileAndSheet:true,parametersRetained:true,reload:true,locale:true,citedRecords:true,heldNotEmpty:true,unsafeActionRejected:true,generationReset:true,bookmarkIdentity:true,overflow:false});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipt.json',out),JSON.stringify({scope:'Rendered deterministic fixtures',receipts,errors},null,2)+'\n');console.log(JSON.stringify({cases:receipts.length,errors}));
}finally{await browser.close();}
