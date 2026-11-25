/* Integration regression for honest dates, held sources and direct station views. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {FAMILIES} from '../../src/mcp_open_data_hk/web/playground-state.js';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8779';
const out=new URL('../../playwright-artifacts/data-quality/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const errors=[],receipts=[];
try{
 for(const width of [390,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let statuses=0,weatherFails=false;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/**',async route=>{
   const request=route.request(),u=new URL(request.url());const path=u.pathname;
   const reply=p=>route.fulfill({json:p});
   if(path==='/api/v1/hkex/latest/status'){statuses++;return reply({coverage:{latestSummaryDate:'2026-10-27'},updater:{lastChecked:'2026-10-30T01:20:00Z',lastSuccessfulRead:'2026-10-27T10:20:00Z',holdCode:'SOURCE_ACCESS_HOLD'}});}
   if(path==='/api/v1/companies/updates/status'){statuses++;return reply({data:{coverage:{acceptedWeeklyFiles:190,discoveredWeeklyFiles:190,addressEntities:1410,addressEligibleObservedEntities:414954,latestAcceptedCoverageEnd:'2026-10-25'},maintenance:{addressQueue:{observed:1612,capacity:{wholeSubset90DayCycleFeasible:false,fullPassMinimumDaysAtCurrentCap:1660}}}}});}
   if(path==='/api/v1/catalogue/datasets'){
    const items=[
      {id:'hk-hko-rss-current-weather-report',title:'Current weather report',titleZhHant:'本港地區天氣報告',sourceUrl:'https://example.gov.hk/hko'},
      {id:'csdi:hko_rcd_1634806665997_63899',title:'HKO station observations',titleZhHant:'天文台測站觀察',sourceUrl:'https://example.gov.hk/csdi'},
    ].map(row=>({...row,provider:'Hong Kong Observatory',providerType:'government',entryKind:'source_dataset',resourceSummary:{byStatus:{queryable:1},total:1}}));
    return reply({items,total:12,nextOffset:null});
   }
   if(path==='/api/v1/districts')return reply({items:[]});
   if(path==='/api/v1/racing/meetings')return reply({data:{items:[]}});
   if(path.endsWith('/schema')||path.endsWith('/query')){
    if(weatherFails)return route.fulfill({status:503,json:{error:{code:'SOURCE_UNAVAILABLE',message:'fixture weather failure'}}});
    const resourceId=path.split('/')[4],resource={id:resourceId,datasetId:'hk-hko-rss-current-weather-report',url:'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en',format:'JSON',catalogue:'DATA.GOV.HK'};
    const row={place:lang==='en'?"King's Park":'京士柏',value:27,unit:'C'},columns=['place','value','unit'];
    return reply({resource,dataset:{id:resource.datasetId,title:'Current weather report',provider:'Hong Kong Observatory',providerType:'government'},schema:{recordPath:'temperature/data',fields:columns.map(name=>({name,types:[name==='value'?'number':'string'],scalarKinds:[name==='value'?'integer':'string']}))},recordCount:1,quality:{semanticVerification:'selected_observation_contract',qualification:{rowCount:1,uniqueStationCount:1,unit:'C'}},observationFreshness:{observedAt:'2026-10-30T12:00:00+08:00'},provenance:[{attribution:'HKO',sourceUrl:resource.url,observedAt:'2026-10-30T12:00:00+08:00',retrievedAt:1793333100,lastCheckedAt:1793333200,publicationDate:'2019-06-27'}],warnings:[],data:{items:[row]},meta:{total:1,nextOffset:null,version:'a'.repeat(64)},presentation:{codec:1,columns,rows:[[{kind:'string',text:row.place,json:JSON.stringify(row.place)},{kind:'integer',text:'27',json:'27'},{kind:'string',text:'C',json:'"C"'}]]}});
   }
   return route.fulfill({status:503,json:{error:{code:'SOURCE_UNAVAILABLE',message:'fixture source unavailable'}}});
  });
  const select=async family=>{
    if(width<=800){const picker=page.locator('#pg-subject');await picker.focus();await picker.selectOption(family);}
    else await page.locator('[data-family="'+family+'"]').press('Enter');
    assert.equal(await page.locator('#pg-subject').inputValue(),family);
    assert.equal(await page.locator('#pg-heading').evaluate(heading=>heading===document.activeElement),true);
  };
  await page.goto(origin+'/playground?lang='+lang,{waitUntil:'domcontentloaded'});
  await page.locator(width<=800?'#pg-subject':'[data-family]').first().waitFor();
  assert.equal(statuses,0,'idle must not fan out status reads');
  assert.equal(await page.locator('#pg-subject optgroup').count(),4);
  assert.equal(await page.locator('#pg-subject option').count(),FAMILIES.length+1);
  await select('hkex_daily');await page.waitForFunction(()=>document.querySelector('#pg-health').textContent.includes('2026-10-27'));
  const health=await page.locator('#pg-health').innerText();assert.match(health,lang==='en'?/newer filings may be missing/:/較新的披露/);assert.equal(statuses,1);
  await select('company_registry');await page.waitForFunction(()=>document.querySelector('#pg-health').textContent.includes('414,954'));
  const company=await page.locator('#pg-health').innerText();assert.match(company,/1,410 \/ 414,954/);assert.match(company,lang==='en'?/not feasible/:/無法/);
  const weatherSearch='/?q=weather&access=sources&provider=government&offset=10&lang='+lang;
  await page.goto(origin+weatherSearch,{waitUntil:'domcontentloaded'});
  const group=page.locator('.mhk-weather-group');
  await group.waitFor();
  assert.equal(await group.locator('details').count(),2);
  for(const row of await group.locator('details').all()){
    if(await row.getAttribute('open')===null)await row.locator('summary').click();
  }
  assert.equal(await group.locator('a[href^="https://example.gov.hk/"]').count(),2);
  const example=page.locator('#directory-weather-examples a').first();
  await example.press('Enter');
  await page.waitForSelector('#pg-table tbody tr');assert.match(await page.locator('#pg-table').innerText(),/27/);
  assert.equal(new URL(page.url()).searchParams.get('discoveryQ'),'weather');assert.equal(new URL(page.url()).searchParams.get('discoveryProvider'),'government');
  assert.equal(new URL(page.url()).searchParams.get('discoveryOffset'),'10');
  assert.match(await page.locator('#pg-scope').innerText(),lang==='en'?/Loaded page only/:/僅已載入的一頁/);
  await page.getByText(lang==='en'?/Sources for this result page: HKO/:/呢頁結果嘅來源：HKO/).waitFor();
  const recordUrl=page.url();
  const dates=await page.locator('#pg-dates').innerText();assert.match(dates,lang==='en'?/Source observation time/:/來源觀察時間/);assert.match(dates,lang==='en'?/Retrieved/:/擷取/);assert.doesNotMatch(dates,/2019-06-27|Observed \/ retrieved/);assert.equal(await page.locator('#pg-filter-options').getAttribute('open'),null);
  assert.match(await page.locator('#pg-warnings').innerText(),lang==='en'?/contract checked/:/規約/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:new URL('station-'+lang+'-'+width+'.png',out).pathname,fullPage:true});
  await page.locator('#pg-back').press('Enter');
  await group.waitFor();assert.equal(new URL(page.url()).searchParams.get('offset'),'10');
  assert.equal(await page.locator('#directory-provider').inputValue(),'government');
  assert.equal(await page.locator('#directory-access').inputValue(),'sources');
  assert.equal(await page.locator('#mhk-discovery-query').inputValue(),'weather');
  weatherFails=true;
  await page.goto(recordUrl,{waitUntil:'domcontentloaded'});
  await page.locator('#pg-recovery summary').waitFor();
  await page.locator('#pg-recovery summary').click();
  await page.getByText(/fixture weather failure/).first().waitFor();
  assert.equal(await page.locator('#pg-output').isVisible(),false);
  await page.goto(origin+'/playground?lang='+lang,{waitUntil:'domcontentloaded'});
  await page.locator(width<=800?'#pg-subject':'[data-family]').first().waitFor();
  for(const family of FAMILIES){
    await select(family);
    assert.equal(await page.locator('#pg-subject').inputValue(),family);
  }
  receipts.push({width,lang,idleStatusReads:0,heldSourceVisible:true,publishedAddressDenominator:true,directStationPreview:true,separateDates:true,overflow:false});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipts.json',out),JSON.stringify({receipts,errors},null,2));console.log(JSON.stringify({receipts,errors}));
}finally{await browser.close();}
