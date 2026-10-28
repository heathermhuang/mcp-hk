import {openSourceExplorer} from './source-explorer-browser.mjs';
/* Archive browser regression: synthetic edge cases or the actual local/served release. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765',real=process.env.WEBB_SDI_REAL==='1';
const out=new URL('../../playwright-artifacts/webb-sdi/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const version='webb-sdi-synthetic-v1',coverage={tables:{sdi:{rows:2}},issuerCount:1,dateRanges:{relDate:['2000-01-01','2000-01-02']}};
const row=id=>({id:'webb:sdi:'+id,serial:'TEST_'+id,issuer_id:'webb:person:100',stock_code:'00005',event_date:'2000-01-01',awareness_date:null,signed_date:'2000-01-02',filed_date:null,published_date:null,discloser:{name1:'Synthetic discloser 香港測試',name2:null,chinese_name:null},before:{long_shares:'9007199254740993.00000001',long_percent:'1.1',short_shares:null,short_percent:null},after:{long_shares:'9007199254740994.00000001',long_percent:'1.2',short_shares:null,short_percent:null},capacities:[{capacity_code:'1',capacity_label:'Synthetic capacity',position:'long',shares:'10'}],events:[{reason:'1',reason_label:'Synthetic reason',position:'long',shsInv:'1'}],revision_links:id==='1'?[{relation:'superseded_by',serial:'TEST_2',filing_id:'webb:sdi:2',resolved:true},{relation:'amends',serial:'ABSENT',resolved:false}]:[],source_fields:{}});
const wrap=(data,nextCursor=null)=>({data:Array.isArray(data)?{items:data}:data,meta:{version,view:'webb_sdi_archive',nextCursor},provenance:[{sourceId:'webb_sdi_archive'}],warnings:[]});
function unzip(bytes){const files=new Map();let p=0;while(bytes.readUInt32LE(p)===0x04034b50){const size=bytes.readUInt32LE(p+18),n=bytes.readUInt16LE(p+26),extra=bytes.readUInt16LE(p+28);const name=bytes.subarray(p+30,p+30+n).toString();const start=p+30+n+extra;files.set(name,bytes.subarray(start,start+size));p=start+size;}return files;}
const receipts=[],errors=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true}),page=await context.newPage();let failed=false;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  if(!real){await context.route('**/api/v1/hkex/archive/**',async r=>{const u=new URL(r.request().url());let data;
   if(u.pathname.endsWith('/notice'))return r.fulfill({status:200,contentType:'text/plain',body:'Synthetic Webb notice for browser fixture'});
   if(u.pathname.endsWith('/status'))data={source:'webb_sdi_archive',state:'available',version,coverage};
   else if(failed)return r.fulfill({status:503,contentType:'application/json',body:'{"error":{"code":"PACK_UNAVAILABLE"}}'});
   else if(u.pathname.endsWith('/issuers')){assert.equal(u.searchParams.get('stockCode'),'00005');data=wrap([{issuer_id:'webb:person:100',name:'Synthetic issuer',first_event:'2000-01-01',last_event:'2000-01-02',archive_filings:2}]);}
   else if(u.pathname.endsWith('/disclosures')){assert.equal(u.searchParams.get('version'),version);data=wrap([row(u.searchParams.has('cursor')?'2':'1')],u.searchParams.has('cursor')?null:'signed-fixture-cursor');}
   else {assert.equal(u.searchParams.get('version'),version);data=wrap(row(u.pathname.endsWith('2')?'2':'1'));}
   await r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
  });}
  await page.goto(origin+'/hkex?lang='+lang);await openSourceExplorer(page);await page.locator('#webb-workspace').waitFor({state:'visible'});
  await page.locator('#webb-search').evaluate(f=>f.requestSubmit());await page.locator('#webb-issuers button').first().click();await page.locator('#webb-list button').first().click();await page.locator('#webb-detail-section').waitFor({state:'visible'});
  assert.equal(await page.locator('#webb-detail-title').evaluate(e=>e===document.activeElement),true);
  assert.match(await page.locator('#webb-detail').innerText(),lang==='en'?/Unknown/:/未知/);
  if(!real){assert.match(await page.locator('#webb-detail').innerText(),/9007199254740993\.00000001/);assert.match(await page.locator('#webb-detail').innerText(),/ABSENT/);await page.locator('#webb-detail button').click();await page.waitForFunction(()=>document.querySelector('#webb-detail-title').textContent.includes('TEST_2'));}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const pending=page.waitForEvent('download');await page.locator('#webb-download').click();const download=await pending;const bytes=await readFile(await download.path()),files=unzip(bytes),manifest=JSON.parse(files.get('manifest.json'));
  assert.equal(manifest.view,'webb_sdi_archive');assert.equal(manifest.scope,'this_page');assert.equal(manifest.rowCount,real?20:1);assert.match(files.get('NOTICE.txt').toString(),/Webb/);
  for(const f of manifest.files)assert.equal(createHash('sha256').update(files.get(f.file)).digest('hex'),f.sha256);
  assert.equal(JSON.parse(files.get('records.json'))[0].filed_date,null);
  await page.locator('#webb-next').click();await page.locator('#webb-previous').waitFor({state:'visible'});assert.equal(await page.locator('#webb-detail-section').isVisible(),false);
  await page.screenshot({path:new URL(`${real?'real':'synthetic'}-${lang}-${width}.png`,out).pathname,fullPage:true});
  if(!real){failed=true;await page.locator('#webb-search').evaluate(f=>f.requestSubmit());await page.waitForFunction(()=>document.querySelector('#webb-message').textContent.length>0);assert.equal(await page.locator('#webb-list-section').isVisible(),false);assert.equal(await page.locator('#webb-detail-section').isVisible(),false);assert.equal(await page.locator('#webb-download').isDisabled(),true);}
  receipts.push({lang,width,realArchive:real,downloadRows:manifest.rowCount,downloadSha256:createHash('sha256').update(bytes).digest('hex'),passed:true});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL(`${real?'real':'synthetic'}-receipts.json`,out),JSON.stringify({receipts,errors},null,2)+'\n');console.log(`Webb SDI: ${receipts.length} ${real?'real archive':'synthetic'} browser journeys passed`);
}finally{await browser.close();}
