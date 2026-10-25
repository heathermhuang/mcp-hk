/* Rendered gate-only acceptance. No provider captures or synthetic racing facts. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:18743';
const output=new URL('../../playwright-artifacts/racing/',import.meta.url);
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[],sourceRequests=[];
try {
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900}});
  const page=await context.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('https://hk.app/**',r=>r.abort());
  await context.route(/https:\/\/[^/]*hkjc\.com\//,r=>{sourceRequests.push(r.request().url());return r.abort();});
  await page.goto(origin+'/racing?lang='+lang);
  await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('html').getAttribute('lang'),lang);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.equal(await page.locator('h1').innerText(),lang==='en'?'Racing source status':'賽馬來源狀態');
  const text=await page.locator('main').innerText();
  assert.match(text,lang==='en'?/No racing dataset is published/:/目前未有發布賽馬資料集/);
  assert.equal(await page.locator('a[download],button:has-text("Download"),form').count(),0);
  await page.keyboard.press('Tab');assert.equal(await page.locator('.mhk-skip-link').evaluate(e=>e===document.activeElement),true);
  if(width===320)await page.screenshot({path:new URL(lang+'-320.png',output).pathname,fullPage:true});
  const status=await page.request.get(origin+'/api/v1/racing/status');
  assert.equal(status.status(),200);
  const body=await status.json();assert.equal(body.data.liveQualified,false);assert.equal(body.data.acceptedVersion,null);
  const denied=await page.request.get(origin+'/api/v1/racing/exports');assert.equal(denied.status(),503);
  receipts.push({lang,width,overflow:false,status:body.data.state,downloadStatus:denied.status()});
  await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(sourceRequests,[]);
 await writeFile(new URL('receipt.json',output),JSON.stringify({origin,scope:'gate-only; no live racing facts',receipts,errors,sourceRequests},null,2));
 console.log(JSON.stringify({scenarios:receipts.length,errors,sourceRequests}));
} finally {await browser.close();}
