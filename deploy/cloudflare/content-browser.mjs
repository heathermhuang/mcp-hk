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
  const transportSearches=[];
  await context.route('**/api/v1/catalogue/datasets?*',route=>{
   const params=new URL(route.request().url()).searchParams;
   if(params.get('q')!=='transport'||params.get('access')!=='sources')return route.continue();
   transportSearches.push(params);
   return route.fulfill({json:{items:[{id:'fixture-bus',title:'Bus route data',titleZhHant:'巴士路線數據'}],total:1,nextOffset:null}});
  });
  const analyticsLabel=lang==='en'?'Analytics settings':'分析數據設定';
  const transportLabel=lang==='en'?'Browse transport datasets':'瀏覽交通數據集';
  for(const path of [...Object.keys(pages),'/docs']){
   await page.goto(origin+path+'?lang='+lang);await page.locator('html[lang="'+lang+'"]').waitFor();
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,path+' '+lang+' '+width);
   const nav=page.locator('.mhk-navbutton');assert.equal(await nav.first().getAttribute('href'),'/playground?lang='+lang);
   if(await page.locator('script[src^="/assets/analytics.js"]').count()){
    const settings=page.locator('footer [data-analytics-settings]');
    assert.equal(await settings.innerText(),analyticsLabel);
    assert.equal(await settings.isVisible(),true);
   }
   if(path==='/privacy'){
    const text=await page.locator('#mhk-legal table').innerText();
    for(const pattern of lang==='en'?[/Automatic website analytics/,/Private MCP usage attribution/,/90 UTC days/,/30 UTC days/,/180 days/,/Rejection stays until changed/]:[/自動網站分析/,/私人 MCP 用量歸因/,/90 個 UTC 日/,/30 個 UTC 日/,/180 日/,/拒絕設定會保留/])assert.match(text,pattern);
    assert.match(await page.locator('meta[name="description"]').getAttribute('content'),lang==='en'?/automatic website analytics/:/自動網站分析/);
    const settings=page.locator('#mhk-legal').getByRole('button',{name:analyticsLabel});
    await settings.focus();await page.keyboard.press('Enter');
    const dialog=page.locator('#mhk-privacy-choice');
    assert.equal(await dialog.evaluate(el=>el.matches(':modal')),true);
    assert.equal(await dialog.locator('a').getAttribute('href'),'/privacy?lang='+lang);
    await page.keyboard.press('Escape');assert.equal(await dialog.isVisible(),false);
   }
   if(path==='/datasets'){
    assert.equal(await page.locator('.dataset-family').count(),families.length);
    for(const row of families)assert.equal(await page.locator('#dataset-'+row.id+' h2').innerText(),row.title[lang]);
    await page.locator('#dataset-racing summary').click();assert.match(await page.locator('#dataset-racing details').innerText(),/hk_racing_status/);
    const link=new URL(await page.locator('#dataset-hkex_daily h2 a').getAttribute('href'),origin);
    assert.equal(link.searchParams.get('lang'),lang);assert.equal(link.pathname,'/playground');assert.equal(JSON.parse(decodeURIComponent(link.hash.slice(3))).family,'hkex_daily');
    await page.screenshot({path:new URL(`directory-${lang}-${width}.png`,out).pathname,fullPage:true});
    const lookupLabel=lang==='en'?'Look up bus stops and routes':'查巴士站及路線';
    const transport=page.locator('#dataset-transport .dataset-actions').getByRole('link',{name:lookupLabel+' →'});
    const legacy=await page.locator('#dataset-transport h2 a').getAttribute('href');
    assert.equal(await transport.getAttribute('href'),legacy);
    await transport.press('Enter');
    const choice=page.locator('[data-family="transport"]');
    await choice.waitFor();
    assert.equal(await choice.getAttribute('aria-pressed'),'true');
    await page.getByRole('button',{name:transportLabel,exact:true}).click();
    await page.locator('#pg-discovery-results').getByRole('button',{name:lang==='en'?'Bus route data':'巴士路線數據'}).waitFor();
    assert.equal(transportSearches.length,1);
    assert.equal(new URL(page.url()).hash,new URL(legacy,origin).hash);
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
