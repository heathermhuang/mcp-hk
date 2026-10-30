/* Whole-site static content/navigation contract. Empty local DB is not data acceptance. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const web=new URL('../../src/mcp_open_data_hk/web/',import.meta.url);
const pages=JSON.parse(await readFile(new URL('discovery.json',web),'utf8')).pages;
const families=JSON.parse(await readFile(new URL('datasets.json',web),'utf8'));
const out=new URL('../../playwright-artifacts/content/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[];
try{
 for(const width of [320,390,768,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  await context.route('https://hk.app/**',r=>r.abort());
  for(const path of [...Object.keys(pages),'/docs']){
   await page.goto(origin+path+'?lang='+lang);await page.locator('html[lang="'+lang+'"]').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,path+' '+lang+' '+width);
   const nav=page.locator('.mhk-navbutton');assert.equal(await nav.first().getAttribute('href'),'/playground?lang='+lang);
   if(path==='/datasets'){
    assert.equal(await page.locator('.dataset-family').count(),families.length);
    for(const row of families)assert.equal(await page.locator('#dataset-'+row.id+' h2').innerText(),row.title[lang]);
    await page.locator('#dataset-racing summary').click();assert.match(await page.locator('#dataset-racing details').innerText(),/hk_racing_status/);
    const link=new URL(await page.locator('#dataset-hkex_daily h2 a').getAttribute('href'),origin);
    assert.equal(link.searchParams.get('lang'),lang);assert.equal(link.pathname,'/playground');assert.equal(JSON.parse(decodeURIComponent(link.hash.slice(3))).family,'hkex_daily');
    await page.screenshot({path:new URL(`directory-${lang}-${width}.png`,out).pathname,fullPage:true});
   }
   if(path==='/sfc')assert.equal(await page.locator('#sfc-ce').isDisabled(),true);
   receipts.push({path,lang,width,overflow:false,sharedNavigation:true});
  }
  await context.close();
 }
 assert.deepEqual(errors,[]);
 await writeFile(new URL('receipt.json',out),JSON.stringify({origin,scope:'static content, locale, navigation and responsive layout; empty local DB is not provider qualification',receipts,errors},null,2)+'\n');
 console.log(JSON.stringify({pages:receipts.length,errors}));
}finally{await browser.close();}
