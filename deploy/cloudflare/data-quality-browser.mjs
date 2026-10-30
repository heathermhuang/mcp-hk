/* Integration regression for honest dates, held sources and direct station views. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {weatherChoices} from '../../src/mcp_open_data_hk/web/source-quality.js';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8779';
const out=new URL('../../playwright-artifacts/data-quality/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const errors=[],receipts=[];
try{
 for(const width of [390,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let statuses=0;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/**',async route=>{
   const request=route.request(),u=new URL(request.url());const path=u.pathname;
   const reply=p=>route.fulfill({json:p});
   if(path==='/api/v1/hkex/latest/status'){statuses++;return reply({coverage:{latestSummaryDate:'2026-10-27'},updater:{lastChecked:'2026-10-30T01:20:00Z',lastSuccessfulRead:'2026-10-27T10:20:00Z',holdCode:'SOURCE_ACCESS_HOLD'}});}
   if(path==='/api/v1/companies/updates/status'){statuses++;return reply({data:{coverage:{acceptedWeeklyFiles:190,discoveredWeeklyFiles:190,addressEntities:1410,addressEligibleObservedEntities:414954,latestAcceptedCoverageEnd:'2026-10-25'},maintenance:{addressQueue:{observed:1612,capacity:{wholeSubset90DayCycleFeasible:false,fullPassMinimumDaysAtCurrentCap:1660}}}}});}
   if(path.endsWith('/schema')||path.endsWith('/query')){
    const resourceId=path.split('/')[4],resource={id:resourceId,datasetId:'hk-hko-rss-current-weather-report',url:'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en',format:'JSON',catalogue:'DATA.GOV.HK'};
    const row={place:lang==='en'?"King's Park":'京士柏',value:27,unit:'C'},columns=['place','value','unit'];
    return reply({resource,dataset:{id:resource.datasetId,title:'Current weather report',provider:'Hong Kong Observatory',providerType:'government'},schema:{recordPath:'temperature/data',fields:columns.map(name=>({name,types:[name==='value'?'number':'string'],scalarKinds:[name==='value'?'integer':'string']}))},recordCount:1,quality:{semanticVerification:'selected_observation_contract',qualification:{rowCount:1,uniqueStationCount:1,unit:'C'}},observationFreshness:{observedAt:'2026-10-30T12:00:00+08:00'},provenance:[{attribution:'HKO',observedAt:'2026-10-30T12:00:00+08:00',retrievedAt:1793333100,lastCheckedAt:1793333200,publicationDate:'2019-06-27'}],warnings:[],data:{items:[row]},meta:{total:1,nextOffset:null,version:'a'.repeat(64)},presentation:{codec:1,columns,rows:[[{kind:'string',text:row.place,json:JSON.stringify(row.place)},{kind:'integer',text:'27',json:'27'},{kind:'string',text:'C',json:'"C"'}]]}});
   }
   return route.fulfill({status:503,json:{error:{code:'SOURCE_UNAVAILABLE',message:'fixture source unavailable'}}});
  });
  await page.goto(origin+'/playground?lang='+lang);await page.waitForSelector('[data-family]');assert.equal(statuses,0,'idle must not fan out status reads');
  await page.locator('[data-family="hkex_daily"]').click();await page.waitForFunction(()=>document.querySelector('#pg-health').textContent.includes('2026-10-27'));
  const health=await page.locator('#pg-health').innerText();assert.match(health,lang==='en'?/newer filings may be missing/:/較新的披露/);assert.equal(statuses,1);
  await page.locator('[data-family="company_registry"]').click();await page.waitForFunction(()=>document.querySelector('#pg-health').textContent.includes('414,954'));
  const company=await page.locator('#pg-health').innerText();assert.match(company,/1,410 \/ 414,954/);assert.match(company,lang==='en'?/not feasible/:/無法/);
  await page.goto(origin+weatherChoices('hk-hko-rss-current-weather-report',lang)[0].href);
  await page.waitForSelector('#pg-table tbody tr');assert.match(await page.locator('#pg-table').innerText(),/27/);
  const dates=await page.locator('#pg-dates').innerText();assert.match(dates,lang==='en'?/Observed/:/觀察/);assert.match(dates,lang==='en'?/Retrieved/:/擷取/);assert.doesNotMatch(dates,/2019-06-27/);
  assert.match(await page.locator('#pg-warnings').innerText(),lang==='en'?/contract checked/:/規約/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:new URL('station-'+lang+'-'+width+'.png',out).pathname,fullPage:true});
  receipts.push({width,lang,idleStatusReads:0,heldSourceVisible:true,publishedAddressDenominator:true,directStationPreview:true,separateDates:true,overflow:false});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipts.json',out),JSON.stringify({receipts,errors},null,2));console.log(JSON.stringify({receipts,errors}));
}finally{await browser.close();}
