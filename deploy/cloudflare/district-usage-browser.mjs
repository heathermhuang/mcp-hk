import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const live=process.env.MCP_HK_VERIFY_LIVE==='1';
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const districts=[{id:'central-western',name:{en:'Central and Western',zhHant:'中西區'}},{id:'southern',name:{en:'Southern',zhHant:'南區'}}];
const days=Array.from({length:31},(_,i)=>({
  date:new Date(Date.UTC(2026,9,26+i)).toISOString().slice(0,10),
  calls:i%7===0?null:i,ok:i%7===0?null:i-1,failed:i%7===0?null:1,unconfirmed:i%7===0?null:0,mcpRequests:i%7===0?null:i+4,
}));
const usage={version:1,days,topTools:{7:[],30:[]},asOf:'2026-11-25T09:00:00Z'};
try{
  for(const width of [390,1280])for(const lang of ['en','zh-Hant']){
    const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await context.route('https://hk.app/**',route=>route.abort());
    await context.route('https://www.googletagmanager.com/**',route=>route.abort());
    if(!live){
      let populations=0,nearby=[];
      await context.route('**/api/v1/districts',route=>route.fulfill({json:{items:districts}}));
      await context.route('**/api/v1/districts/*/statistics',route=>{
        const id=new URL(route.request().url()).pathname.split('/')[4],district=districts.find(row=>row.id===id);
        populations++;
        return route.fulfill({json:{data:{name:district.name,population:district.id==='southern'?200000:232200,
          referencePeriod:2024,areaKm2:12.55,populationDensity:18510},provenance:[],warnings:[]}});
      });
      await context.route('**/api/v1/addresses/search?*',route=>route.fulfill({json:{data:{items:[
        {id:'exact-address',address:{en:'Fixture Address',zhHant:'測試地址'},districtId:'central-western',latitude:22.28,longitude:114.15},
      ]}}}));
      await context.route('**/api/v1/restaurants?*',route=>{
        nearby.push(new URL(route.request().url()).searchParams.get('radiusM'));
        return route.fulfill({json:{data:{items:[]},meta:{},provenance:[],warnings:[]}});
      });
      await page.goto(origin+'/demo?lang='+lang,{waitUntil:'domcontentloaded'});
      const district=page.locator('#mhk-district'),value=page.locator('.mhk-pop-value');
      await district.locator('option[value=southern]').waitFor({state:'attached'});
      await district.selectOption('southern');await value.getByText(/200,000/).waitFor();
      await page.locator('#mhk-query').fill('Fixture Address');await page.locator('#mhk-query').press('Enter');
      await page.locator('#mhk-candidates button').first().press('Enter');
      await value.getByText(/232,200/).waitFor();
      const previous=populations,year=await page.locator('[data-dynamic=year]').innerText();
      await page.locator('#mhk-radius').selectOption('1000');
      await page.waitForFunction(()=>document.querySelector('#mhk-address-form button').disabled===false);
      assert.deepEqual(nearby,['500','1000']);assert.equal(populations,previous);
      assert.equal(await page.locator('[data-dynamic=year]').innerText(),year);
      assert.match(await value.innerText(),/232,200/);
      await page.locator('#mhk-change-address').press('Enter');
      assert.equal(await page.locator('#mhk-query').evaluate(el=>el===document.activeElement),true);
      await context.route('**/api/v1/usage',route=>route.fulfill({json:usage}));
    }
    const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/usage'&&r.ok());
    await page.goto(origin+'/usage?lang='+lang,{waitUntil:'domcontentloaded'});
    const snapshot=await (await response).json();
    await page.locator('#usage-history').waitFor();
    const format=new Intl.NumberFormat(lang);
    for(const period of [7,30]){
      await page.locator('#usage-period').selectOption(String(period));
      const selected=snapshot.days.slice(-period-1,-1).filter(day=>day.calls!==null);
      for(const [field,id] of [['calls','period-calls'],['ok','outcome-ok'],['failed','outcome-failed'],['unconfirmed','outcome-unconfirmed']]){
        const expected=selected.length?format.format(selected.reduce((sum,day)=>sum+day[field],0)):'—';
        assert.equal(await page.locator('#usage-'+id).innerText(),expected);
      }
    }
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    assert.deepEqual(errors,[]);
    await context.close();
  }
  console.log(live?'Live 7- and 30-day dashboard totals matched the usage response.':'District scope and 7- and 30-day usage totals passed in both locales and widths.');
}finally{await browser.close();}
