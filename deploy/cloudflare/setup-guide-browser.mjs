import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
try{
  for(const width of [390,1280])for(const lang of ['en','zh-Hant']){
    const context=await browser.newContext({viewport:{width,height:900},permissions:['clipboard-read','clipboard-write']});
    const page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await context.route('https://hk.app/**',route=>route.abort());
    await context.route('https://www.googletagmanager.com/**',route=>route.abort());
    await page.goto(origin+'/guides/connect-ai-to-hong-kong-data?lang='+lang,{waitUntil:'domcontentloaded'});
    const guide=page.locator('#article'),locations={};
    assert.match(await guide.innerText(),/hk_district_statistics.*central-western/);
    for(const client of ['codex','claude','cursor','other']){
      const target=guide.locator('a[href^="/connect?client='+client+'"]');
      locations[client]=await target.getAttribute('href');
      assert.equal(new URL(locations[client],origin).hash,'#client-settings');
    }
    for(const [client,location] of Object.entries(locations)){
      await page.goto(origin+location,{waitUntil:'domcontentloaded'});
      const selected=page.locator('[data-client="'+client+'"]');
      assert.equal(await selected.getAttribute('aria-pressed'),'true');
      assert.match(await page.locator('[data-i18n=connectionSuccess]').innerText(),/hk_district_statistics.*central-western/);
      assert.ok((await page.locator('#mhk-install').innerText()).includes('/mcp'));
      assert.equal(new URL(page.url()).searchParams.get('lang'),lang);
    }
    await page.locator('[data-client=cursor]').press('Enter');
    assert.equal(new URL(page.url()).searchParams.get('client'),'cursor');
    await page.reload({waitUntil:'domcontentloaded'});
    assert.equal(await page.locator('[data-client=cursor]').getAttribute('aria-pressed'),'true');
    await page.goto(origin+'/guides/hong-kong-open-data-api?lang='+lang,{waitUntil:'domcontentloaded'});
    const copy=page.locator('#article .mhk-example-actions button').first();
    await copy.press('Enter');
    assert.match(await page.evaluate(()=>navigator.clipboard.readText()),/central-western\/statistics/);
    const operation=page.locator('#article a[href*="operation-POST"][href$="query"]');
    await operation.first().press('Enter');
    const details=page.locator('details.docs-operation[open]').filter({hasText:'/api/v1/resources/{resourceId}/query'}).first();
    await details.waitFor();
    assert.match(await details.innerText(),/temperature\/data/);
    assert.match(await details.innerText(),/provenance/);
    await details.locator('.mhk-example-actions button').press('Enter');
    const command=await page.evaluate(()=>navigator.clipboard.readText());
    assert.match(command,/curl -fsS.*temperature\/data.*\/query/);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);await context.close();
  }
  console.log('Client links, district success check, copyable examples and HTTP deep links passed in both locales and widths.');
}finally{await browser.close();}
