import {openSourceExplorer} from './source-explorer-browser.mjs';
/* Fabricated accepted-reader responses; no SFC source access or permission claim. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const out=new URL('../../playwright-artifacts/sfc/',import.meta.url);await mkdir(out,{recursive:true});
const version='sfc-'+'a'.repeat(32),fact={ce:'ZZZ001',nameEn:'FABRICATED CORPORATE OBSERVATION',nameZhHant:'虛構法團觀察紀錄',statusLabel:'Unknown overall status',observedAt:'2026-10-26T00:00:00Z',sourceCutoff:{raw:null,precision:'unknown'},activities:[{label:'Fixture dealing activity',statusLabel:'Fixture active',start:{raw:'2020-01',precision:'month'},end:{raw:null,precision:'unknown'}}]};
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[],sourceRequests=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let available=true,fail=false,reads=0;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());await context.route(/https:\/\/apps\.sfc\.hk\//,r=>{sourceRequests.push(r.request().url());return r.abort();});
  await context.route('**/api/v1/sfc/**',r=>{const u=new URL(r.request().url());
   if(u.pathname.endsWith('/status'))return r.fulfill({contentType:'application/json',body:JSON.stringify({data:{sourceId:'sfc_register',acceptedVersion:available?version:null,enabledModes:available?['rest','browser']:[],historyAvailable:available,state:available?'available':'policy_unavailable'}})});
   if(u.pathname.endsWith('/history')){assert.equal(u.searchParams.get('version'),version);return r.fulfill({contentType:'application/json',body:JSON.stringify({data:[{ce:'ZZZ001',version,observedAt:fact.observedAt}],meta:{version,nextCursor:null}})});}
   reads++;assert.equal(u.searchParams.get('version'),version);
   return r.fulfill({status:fail?503:200,contentType:'application/json',body:JSON.stringify(fail?{error:{code:'SFC_POLICY_CHANGED'}}:{data:fact,meta:{version,view:'sfc_observation'}})});
  });
  await page.goto(origin+'/sfc?lang='+lang);await openSourceExplorer(page);await page.locator('#sfc-ce').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#sfc-ce').disabled);
  assert.equal(reads,0,'capability checks never collect or fetch a corporation');assert.match(await page.locator('#sfc-live-verify').innerText(),lang==='en'?/Read official/:/讀取官方/);assert.equal(await page.locator('#sfc-archive-ce').isEnabled(),true);
  await page.locator('#sfc-ce').fill('ZZZ001');await page.locator('#sfc-live-verify').click();await page.locator('#sfc-live-record').waitFor({state:'visible'});
  assert.equal(await page.locator('#sfc-live-record').evaluate(e=>e===document.activeElement),true);
  assert.match(await page.locator('#sfc-live-record').innerText(),new RegExp(version));assert.match(await page.locator('#sfc-live-record').innerText(),lang==='en'?/Unknown/:/未知/);
  assert.equal(new URL(page.url()).searchParams.get('ce'),'ZZZ001');assert.equal(new URL(page.url()).searchParams.get('version'),version);
  await page.locator('#sfc-observation-history').click();await page.locator('#sfc-live-record ul a').waitFor({state:'visible'});assert.equal(new URL(await page.locator('#sfc-live-record ul a').getAttribute('href'),origin).searchParams.get('version'),version);assert.match(await page.locator('#sfc-live-status').innerText(),lang==='en'?/not a complete regulatory/:/並非完整監管/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if(width===320)await page.screenshot({path:new URL('active-'+lang+'-320.png',out).pathname,fullPage:true});
  await page.locator('.mhk-language').click();await page.locator('#sfc-live-record').waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('#sfc-live-record').hidden&&document.querySelector('#sfc-live-record').textContent.includes('ZZZ001'));
  assert.equal(new URL(page.url()).searchParams.get('version'),version);assert.equal(await page.locator('#sfc-ce').inputValue(),'ZZZ001');
  fail=true;await page.locator('#sfc-live-verify').click();await page.waitForFunction(()=>/could not|無法/.test(document.querySelector('#sfc-live-status').textContent));assert.equal(await page.locator('#sfc-live-record').isVisible(),true,'failure retains the dated prior display');
  available=false;await page.reload();await openSourceExplorer(page);await page.waitForFunction(()=>/unavailable|暫未/.test(document.querySelector('#sfc-live-status').textContent));assert.equal(await page.locator('#sfc-ce').isDisabled(),true);assert.equal(await page.locator('#sfc-archive-ce').isEnabled(),true);
  if(width===320)await page.screenshot({path:new URL(lang+'-320.png',out).pathname,fullPage:true});
  receipts.push({lang,width,fixtureOnly:true,identityAndVersionPinned:true,languageStateRetained:true,priorDataRetainedOnFailure:true,deniedModeClosed:true,archiveIndependent:true,overflow:false});await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(sourceRequests,[]);await writeFile(new URL('receipts.json',out),JSON.stringify({receipts,errors,sourceRequests},null,2)+'\n');console.log(`SFC: ${receipts.length} rendered fixture journeys passed`);
}finally{await browser.close();}
