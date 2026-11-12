/* Real browser load ordering; every production-host request is intercepted locally. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
try{
  for(const browserOptOut of [false,true]){
    const context=await browser.newContext(),page=await context.newPage();
    await context.addInitScript(({browserOptOut})=>{
      if(browserOptOut)Object.defineProperty(navigator,'globalPrivacyControl',{get:()=>true});
      else localStorage.setItem('mhk-analytics-choice',JSON.stringify({version:1,allowed:false,at:1}));
    },{browserOptOut});
    const queries=[],errors=[];page.on('pageerror',error=>errors.push(error.message));
    await context.route('**/*',async route=>{
      const url=new URL(route.request().url());
      if(url.origin!=='https://mcp.hk')return route.abort();
      if(url.pathname==='/api/v1/catalogue/datasets'){
        queries.push(await route.request().allHeaders());
        return route.fulfill({json:{items:[],total:0,nextOffset:null}});
      }
      if(url.pathname==='/assets/site-config.json')return route.fulfill({json:{googleAnalyticsId:'G-TEST123456'}});
      if(url.pathname==='/assets/privacy-signal.js')await new Promise(resolve=>setTimeout(resolve,300));
      return route.fulfill({response:await route.fetch({url:origin+url.pathname+url.search})});
    });
    await page.goto('https://mcp.hk/?q=schools&lang=en');
    await page.waitForFunction(()=>document.querySelector('#directory-results')?.getAttribute('aria-busy')==='false');
    assert.equal(queries.length,1);
    assert.equal(queries[0]['x-mcp-analytics-opt-out'],'1');
    assert.match(queries[0].cookie,/__Host-mhk_analytics=off/);
    assert.equal(await page.locator('script[src*="googletagmanager"]').count(),0);
    assert.deepEqual(errors,[]);
    await context.close();
  }
  console.log('Delayed ordered privacy script preserves stored and browser opt-outs before data queries. All requests intercepted; no production analytics sent.');
}finally{await browser.close();}
