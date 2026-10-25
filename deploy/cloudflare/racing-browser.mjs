/* Deterministic rendered production contracts. All data below is invented; zero provider traffic. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:18743';
const output=new URL('../../playwright-artifacts/racing/',import.meta.url);await mkdir(output,{recursive:true});
const version='racing-results-v1-'+'a'.repeat(64),rid='hkjc:meeting:v1:2026-01-01:HV:01';
const horse={id:'hkjc:horse:TEST_ONLY',name:'FIXTURE HORSE WITH A LONG SOURCE NAME',nameZhHant:'測試用長名稱馬匹'};
const row={placingRaw:'1',placing:1,status:'finished',horseNumber:'6',horse,jockey:{id:'hkjc:jockey:TEST',name:'Fixture jockey',nameZhHant:'測試騎師'},trainer:{id:'hkjc:trainer:TEST',name:'Fixture trainer',nameZhHant:'測試練馬師'},draw:'1',timeSeconds:'100.39',weightLb:'128',winOddsFinal:'2.9'};
const meeting={id:'hkjc:meeting:v1:2026-01-01:HV',date:'2026-01-01',venue:'HV'};
const coverage={observedRaces:1,expectedRaces:1,resultRows:1};
const race={id:rid,number:1,name:'FIXTURE HANDICAP',nameZhHant:'測試讓賽',distanceM:1650,goingRaw:'GOOD',goingZhHant:'好地',courseRaw:'TURF',courseZhHant:'草地',results:[row],provenance:[{observed:'2026-10-25T00:00:00Z'}]};
const version2='racing-results-v1-'+'b'.repeat(64),meeting2={id:'hkjc:meeting:v1:2025-12-31:ST',date:'2025-12-31',venue:'ST'},race2={...race,id:'hkjc:meeting:v1:2025-12-31:ST:01',name:'SECOND FIXTURE HANDICAP',nameZhHant:'第二測試讓賽'};
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[],sourceRequests=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await context.route('https://hk.app/**',r=>r.abort());await context.route(/https:\/\/[^/]*hkjc\.com\//,r=>{sourceRequests.push(r.request().url());return r.abort();});
  let participantRequests=0,unavailableRequests=0,participantMode='once';
  await context.route('**/api/v1/racing/**',async route=>{const requested=new URL(route.request().url()),path=requested.pathname;let body;if(requested.searchParams.get('day')==='2026-01-02'){unavailableRequests++;return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:{code:'RACING_DATA_NOT_READY'}})});}
   if(path.includes('/participants/')&&(++participantRequests===1||participantMode==='always'))return route.fulfill({status:503,headers:{'Retry-After':'0'},contentType:'application/json',body:JSON.stringify({error:{code:'SERVICE_RECOVERING'}})});
   if(path.endsWith('/status'))body={data:{state:'available',meetings:[{meeting,version,coverage},{meeting:meeting2,version:version2,coverage}]}};
   else if(path.endsWith('/results'))body={data:requested.searchParams.get('version')===version2?race2:race,meta:{version:requested.searchParams.get('version')||version},coverage};
   else if(path.includes('/participants/'))body={data:{identity:horse,appearances:[{raceId:rid,raceNumber:1,horse,placing:1,status:'finished'}]},meta:{version}};
   else body=requested.searchParams.get('version')===version2?{data:{meeting:meeting2,items:[race2]},meta:{version:version2},coverage}:{data:{meeting,items:[race]},meta:{version},coverage};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto(origin+'/racing?lang='+lang);await page.locator('#rows tr').waitFor();
  assert.equal(await page.locator('html').getAttribute('lang'),lang);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('#race-title').innerText(),lang==='en'?'Race 1 · FIXTURE HANDICAP':'第 1 場 · 測試讓賽');
  assert.match(await page.locator('#rows').innerText(),/100\.39/);assert.match(await page.locator('#download').getAttribute('href'),new RegExp(version));
  await page.keyboard.press('Tab');assert.equal(await page.locator('.mhk-skip-link').evaluate(e=>e===document.activeElement),true);
  await page.getByRole('button',{name:lang==='en'?horse.name:horse.nameZhHant,exact:true}).click();await page.locator('#participant:not([hidden])').waitFor();
  assert.equal(await page.locator('#participant-title').innerText(),lang==='en'?horse.name:horse.nameZhHant);assert.equal(participantRequests,2);assert.equal(await page.locator('#download').getAttribute('download'),'racing-results.zip');
  await page.locator('#back').click();await page.locator('#detail:not([hidden])').waitFor();
  participantMode='always';participantRequests=0;await page.getByRole('button',{name:lang==='en'?horse.name:horse.nameZhHant,exact:true}).click();await page.locator('#message').filter({hasText:lang==='en'?'service is recovering':'服務正在恢復'}).waitFor();assert.equal(participantRequests,3);assert.equal(await page.locator('#detail').isVisible(),true);participantMode='once';
  await page.locator('#racing-day').fill('2026-01-02');await page.locator('#meeting-search button').click();await page.locator('#message').filter({hasText:lang==='en'?'No accepted data':'尚未有已驗證資料'}).waitFor();assert.equal(await page.locator('#detail').isVisible(),false);assert.equal(unavailableRequests,1);await page.locator('#racing-venue').selectOption('HV');await page.locator('#racing-day').fill('2026-01-01');await page.locator('#meeting-search button').click();await page.locator('#rows tr').waitFor();if(width===320)await page.screenshot({path:new URL(lang+'-320.png',output).pathname,fullPage:true});
  await page.locator('#meeting').selectOption(version2);await page.locator('#race-title').filter({hasText:lang==='en'?'SECOND FIXTURE':'第二測試'}).waitFor();await page.locator('#language').click();await page.waitForURL(u=>u.searchParams.get('lang')===(lang==='en'?'zh-Hant':'en'));await page.locator('#rows tr').waitFor();assert.equal(await page.locator('#meeting').inputValue(),version2);assert.equal(new URL(page.url()).searchParams.get('version'),version2);receipts.push({lang,width,overflow:false,pinnedVersion:true,raceAndParticipantNavigation:true,transientRecoveryRetried:true,boundedRecoveryAttempts:3,sourceFailureNotRetried:true,downloadLinkPinned:true,fixtureOnly:true});await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(sourceRequests,[]);await writeFile(new URL('receipt.json',output),JSON.stringify({origin,scope:'rendered public contracts with invented data; no provider acceptance claim',receipts,errors,sourceRequests},null,2));console.log(JSON.stringify({scenarios:receipts.length,errors,sourceRequests}));
}finally{await browser.close();}
