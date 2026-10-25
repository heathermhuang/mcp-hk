/* Synthetic normalized notices only; never contacts HKEX. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const out=new URL('../../playwright-artifacts/hkex/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const version='hkex-'+'a'.repeat(32),w={issuer_id:'TEST_ISSUER',start:'2026-10-12',end:'2026-10-19',basis:'filed',channel:'dion',timezone:'Asia/Hong_Kong'};
const day=value=>({value,precision:value?'day':'unknown',timezone:'Asia/Hong_Kong'});
const securities=[{id:'TEST_SEC',source_id:'TEST_SEC',stock_code:'00001',share_class:'ordinary A',name:'Synthetic A'}];
const row=serial=>({serial,subject:'Synthetic example',state:serial==='A'?'superseded':'withdrawn',event_date:day('2020-01-01'),filed_date:day('2026-10-14'),published_date:day(null),withdrawn_date:day(serial==='B'?'2026-10-15':null),securities,interests:[{security_id:'TEST_SEC',instrument:'issuer_shares',position:'long',nature:'deemed',phase:'after',capacity_code:'TEST_CAP',shares:'9007199254740993.000000000000000001',percentage:null,unit:'shares'}],revision_links:[{older:'A',newer:'B',resolved:true}],capture:{observed_at:'2026-10-20T00:00:00Z'}});
const coverage={window:w,complete:true,pages:1,comprehensiveIncremental:false};const receipts=[],errors=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();let gated=false;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/hkex/**',async r=>{const u=new URL(r.request().url());let data;
   if(u.pathname.endsWith('/status'))data=gated?{source:'hkex_di',state:'source_unqualified',acceptedVersion:null,modes:{browser:'unknown'},coverage:null}:{source:'hkex_di',state:'accepted',acceptedVersion:version,modes:{browser:'allowed'},coverage};
   else if(u.pathname.endsWith('/issuers')){assert.equal(u.searchParams.get('stockCode'),'00001');assert.equal(u.searchParams.get('version'),version);data={version,data:[{id:'TEST_ISSUER',name:'Synthetic issuer 香港測試',securities}]};}
   else if(u.pathname.endsWith('/disclosures')){assert.equal(u.searchParams.get('basis'),'filed');assert.equal(u.searchParams.get('version'),version);data={version,coverage,data:[row('A')],nextCursor:null};}
   else{assert.equal(u.searchParams.get('version'),version);data={version,data:row(u.pathname.split('/').pop())};}
   await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto(origin+'/hkex?lang='+lang);await page.locator('#hkex-workspace').waitFor({state:'visible'});
  await page.locator('#hkex-stock').fill('00001');await page.locator('#hkex-search').evaluate(f=>f.requestSubmit());await page.locator('#hkex-issuers button').click();await page.locator('#hkex-list button').click();
  await page.locator('#hkex-detail').waitFor({state:'visible'});assert.equal(await page.locator('#hkex-detail-heading').evaluate(e=>e===document.activeElement),true);
  assert.match(await page.locator('#hkex-interests').innerText(),/9007199254740993\.000000000000000001/);
  assert.match(await page.locator('#hkex-dates').innerText(),lang==='en'?/Unknown/:/未知/);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('a[download]').count(),0);assert.equal(await page.locator('a[href*="di.hkex.com.hk"]').count(),0);
  await page.locator('#hkex-revisions button').click();await page.waitForFunction(()=>document.querySelector('#hkex-detail-heading').textContent.startsWith('B'));
  assert.match(await page.locator('#hkex-dates').innerText(),lang==='en'?/Withdrawn/:/已撤回/);
  await page.screenshot({path:new URL(`${lang}-${width}-synthetic.png`,out).pathname,fullPage:true});
  gated=true;await page.locator('#hkex-retry').click();await page.locator('#hkex-workspace').waitFor({state:'hidden'});
  assert.equal(await page.locator('#hkex-list button').count(),0);assert.equal(await page.locator('#hkex-detail').isVisible(),false);
  receipts.push({lang,width,synthetic:true,passed:true});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipts.json',out),JSON.stringify({receipts,errors},null,2)+'\n');console.log(`HKEX: ${receipts.length} rendered synthetic journeys passed`);
}finally{await browser.close();}
