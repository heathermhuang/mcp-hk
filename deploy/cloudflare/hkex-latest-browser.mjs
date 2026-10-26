import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765',real=process.env.HKEX_DAILY_REAL==='1',pace=Number(process.env.HKEX_DAILY_PACE_MS||0);
const out=new URL('../../playwright-artifacts/hkex-latest/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const version='hkex-daily-'+'a'.repeat(32),recordId='hkex:daily:2026-10-23:2:'+'a'.repeat(20);
const row={id:recordId,source:'hkex_daily_summary',summary_date:'2026-10-23',event_date:'2000-01-01',filed_date:null,form:'3A',stock_code:'00595',issuer_name:'Synthetic issuer 香港測試',discloser:'Synthetic filer',serial:'DA20261023E00001',share_class:'Ordinary shares',reason_as_disclosed:'1101(L)',shares_involved_as_disclosed:'1,000(L)',average_price_as_disclosed:'HKD 1.2000',interests:[{phase:'before',position:'long',shares:'9007199254740993.00000001',percentage:'1.00'},{phase:'after',position:'long',shares:'9007199254740994.00000001',percentage:'1.01'}],revision:{remarks:'Amendment to DA20261022E00001'},source_url:'https://di.hkex.com.hk/di/summary/DSM20261023C2.htm'};
const envelope=(data,cursor=null)=>({data:Array.isArray(data)?{items:data}:data,meta:{version,view:'hkex_daily_summary',nextCursor:cursor,queryCoverage:{unobservedReports:[{summaryDate:'2026-10-19',category:1}]}},provenance:[{sourceId:'hkex_daily_summary',licenceClaimed:false}],warnings:[]});
function unzip(b){const files=new Map();let at=0;while(b.readUInt32LE(at)===0x04034b50){const size=b.readUInt32LE(at+18),n=b.readUInt16LE(at+26),extra=b.readUInt16LE(at+28),name=b.subarray(at+30,at+30+n).toString(),start=at+30+n+extra;files.set(name,b.subarray(start,start+size));at=start+size;}return files;}
const receipts=[],errors=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true}),page=await context.newPage();let fail=false,held=false;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  if(!real)await context.route('**/api/v1/hkex/latest/**',async r=>{const u=new URL(r.request().url());let data;
   if(u.pathname.endsWith('/notice'))return r.fulfill({status:200,contentType:'text/plain',body:'Source: Hong Kong Exchanges and Clearing Limited (HKEX). Test notice; licence not asserted.'});
   if(u.pathname.endsWith('/status'))data={source:'hkex_daily_summary',state:'available',version,coverage:{latestSummaryDate:'2026-10-23',rows:2},updater:{lastChecked:'2026-10-26T00:00:00Z',lastSuccessfulRead:'2026-10-26T00:00:00Z',holdCode:held?'SOURCE_ACCESS_HOLD':null,lastRun:{state:held?'failed':'unchanged'}}};
   else if(fail)return r.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"PACK_UNAVAILABLE"}}'});
   else if(u.pathname.endsWith('/disclosures')){assert.equal(u.searchParams.get('version'),version);data=envelope([row],u.searchParams.has('cursor')?null:'signed-fixture-cursor');}
   else data=envelope(row);
   await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto(origin+'/hkex?lang='+lang);await page.locator('#daily-workspace').waitFor({state:'visible'});await page.locator('#daily-list button').first().click();await page.locator('#daily-detail-section').waitFor({state:'visible'});
  assert.equal(await page.locator('#daily-detail-title').evaluate(e=>e===document.activeElement),true);
  assert.match(await page.locator('#daily-detail').innerText(),lang==='en'?/Unknown/:/未知/);
  if(!real){assert.match(await page.locator('#daily-detail').innerText(),/9007199254740993\.00000001/);assert.match(await page.locator('#daily-gaps').innerText(),/2026-10-19/);}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const waiting=page.waitForEvent('download');await page.locator('#daily-export').click();const d=await waiting,b=await readFile(await d.path()),files=unzip(b),manifest=JSON.parse(files.get('manifest.json'));assert.equal(manifest.view,'hkex_daily_summary');assert.equal(manifest.rowCount,real?20:1);assert.match(files.get('NOTICE.txt').toString(),/HKEX/);for(const f of manifest.files)assert.equal(createHash('sha256').update(files.get(f.file)).digest('hex'),f.sha256);assert.equal(JSON.parse(files.get('records.json'))[0].filed_date,null);
  await page.locator('#daily-next').click();await page.locator('#daily-previous').waitFor({state:'visible'});assert.equal(await page.locator('#daily-detail-section').isVisible(),false);
  await page.locator('#daily-stock').fill('00595');await page.locator('#daily-search').evaluate(f=>f.requestSubmit());await page.waitForFunction(()=>document.querySelector('#daily-list button')?.textContent.includes('00595'));await page.locator('#daily-list button').first().click();await page.locator('#daily-detail-section').waitFor({state:'visible'});
  await page.screenshot({path:new URL(`${real?'real':'synthetic'}-${lang}-${width}.png`,out).pathname,fullPage:true});
  if(!real){held=true;await page.locator('#daily-refresh').click();await page.waitForFunction(()=>document.querySelector('#daily-warning').textContent.length>0);assert.equal(await page.locator('#daily-list button').count(),1);fail=true;await page.locator('#daily-search').evaluate(f=>f.requestSubmit());await page.waitForFunction(()=>document.querySelector('#daily-message').textContent.length>0);assert.equal(await page.locator('#daily-list button').count(),0);assert.equal(await page.locator('#daily-export').isDisabled(),true);}
  receipts.push({lang,width,realData:real,downloadRows:manifest.rowCount,zipSha256:createHash('sha256').update(b).digest('hex'),passed:true});await context.close();if(pace)await new Promise(r=>setTimeout(r,pace));
 }
 assert.deepEqual(errors,[]);await writeFile(new URL(`${real?'real':'synthetic'}-receipts.json`,out),JSON.stringify({receipts,errors},null,2)+'\n');console.log(`HKEX latest: ${receipts.length} ${real?'real':'synthetic'} browser journeys passed`);
}finally{await browser.close();}
