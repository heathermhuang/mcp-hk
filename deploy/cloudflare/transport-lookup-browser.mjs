import assert from 'node:assert/strict';
import {chromium} from 'playwright';
import {encodeRecipe} from '../../src/mcp_open_data_hk/web/playground-state.js';

const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const stops=[
  {stopId:'261',name:{en:'Lan Kwai Fong',zhHant:'蘭桂坊'},operators:['CTB'],latitude:22.28,longitude:114.15},
  {stopId:'262',name:{en:'Lan Kwai Fong',zhHant:'蘭桂坊'},operators:['KMB'],latitude:22.29,longitude:114.16},
  {stopId:'263',name:{en:'Seymour Road',zhHant:'西摩道'},operators:['CTB','KMB'],latitude:22.27,longitude:114.14},
];
const provenance=[{sourceUrl:'https://static.data.gov.hk/example/routes.xml',retrievedAt:1700000000,sourceModified:'2026-11-01'}];
const route={operator:'CTB',route:'12',origin:{en:'Central',zhHant:'中環'},destination:{en:'Mid-Levels',zhHant:'半山'},specialType:'0',sourceUpdatedAt:'2026-11-01'};
const outbound={route,direction:'outbound',board:stops[0],alight:stops[2]};
const envelope=data=>({data,provenance,meta:{indexVersion:'fixture-index'}});
try{
  for(const width of [390,1280])for(const locale of ['en','zh-Hant']){
    const context=await browser.newContext({viewport:{width,height:820},timezoneId:'America/Los_Angeles'});
    const page=await context.newPage(),requests=[],errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    let timedOut=false,predictedAt;
    await context.route('https://hk.app/**',entry=>entry.abort());
    await context.route('**/api/v1/transport/**',async entry=>{
      const {pathname,searchParams}=new URL(entry.request().url());
      const body=entry.request().postDataJSON();
      requests.push({pathname,body,query:Object.fromEntries(searchParams)});
      if(pathname.endsWith('/stops')){
        const query=searchParams.get('q');
        const items=/Seymour|西摩道/.test(query)?[stops[2]]:stops.slice(0,2);
        assert.equal(searchParams.get('limit'),'20');
        return entry.fulfill({json:envelope({items,totalMatched:items.length})});
      }
      if(pathname.endsWith('/261/routes'))return entry.fulfill({
        json:envelope({items:[{...route,direction:'outbound'},{...route,direction:'inbound'}]}),
      });
      assert.equal(pathname,'/api/v1/transport/journeys');
      const base={
        originCandidates:[stops[0]],destinationCandidates:[stops[2]],referenceCandidateCount:6,
        totalDepartureChoices:6,coverage:{referenceIndexStale:false},
      };
      assert.deepEqual(body,{origin:'td:stop:261',destination:'td:stop:263',includeArrivals:body.includeArrivals,limit:5});
      if(!body.includeArrivals)return entry.fulfill({json:envelope({...base,items:[outbound]})});
      if(timedOut)return entry.fulfill({status:504,json:{error:{code:'SOURCE_TIMEOUT'}}});
      const now=Date.now()/1000;predictedAt=now+60;
      const live={...outbound,arrivalStatus:'live',arrivalCheckedAt:now,arrivals:{
        items:[{eta:'raw fixture timing'}],transport:{cacheTTLSeconds:3,freshUntil:now+30,sourceTimestamp:new Date(now*1000).toISOString()},
      },earliestPredictedDeparture:new Date((predictedAt+8*3600)*1000).toISOString().slice(0,-1).replace('T',' ')};
      return entry.fulfill({json:envelope({...base,items:[
        live,
        {...live,earliestPredictedDeparture:null,arrivals:{...live.arrivals,items:[],transport:{...live.arrivals.transport,cacheTTLSeconds:20}}},
        {...outbound,arrivalStatus:'unavailable',arrivalError:{code:'SOURCE_RESTRICTED'}},
        {...outbound,arrivalStatus:'unchecked',uncheckedReason:'comparison_deadline'},
        {...outbound,arrivalStatus:'unavailable',arrivalError:{code:'STALE_SOURCE'}},
      ],coverage:{acceptedArrivalChecks:2,failed:2,unchecked:1,verifiedNotServingOrder:0,complete:false,referenceIndexStale:true,uncheckedReasons:{comparison_deadline:1}}})});
    });
    await page.goto(origin+'/playground?lang='+locale+encodeRecipe({v:1,family:'transport',lang:locale}),{waitUntil:'domcontentloaded'});
    const panel=page.locator('.pg-bus'),boarding=page.locator('#pg-bus-origin'),alighting=page.locator('#pg-bus-destination');
    const find=panel.getByRole('button',{name:locale==='en'?'Find direct routes':'搵直達路線'});
    const check=panel.getByRole('button',{name:locale==='en'?'Check live arrivals':'查即時到站預測'});
    await boarding.fill(locale==='en'?'Lan Kwai Fong':'蘭桂坊');await boarding.press('Enter');
    const second=panel.getByRole('button',{name:/td:stop:262/});
    await second.waitFor();
    assert.equal(requests.length,1);
    await panel.getByRole('button',{name:/td:stop:261/}).press('Enter');
    await panel.getByText(locale==='en'?'Outbound · Central → Mid-Levels':'去程 · 中環 → 半山',{exact:true}).waitFor();
    assert.equal(await find.isDisabled(),true);
    await alighting.fill(locale==='en'?'Seymour Road':'西摩道');await alighting.press('Enter');
    await panel.getByRole('button',{name:/td:stop:263/}).press('Enter');
    assert.equal(await check.count(),0);
    await find.press('Enter');
    await panel.getByText(locale==='en'?/Showing 1 of 6 reference/:/顯示 1 個參考選項，共 6 個/).waitFor();
    assert.equal(requests.filter(r=>r.body?.includeArrivals).length,0);
    await check.press('Enter');
    const partial=panel.getByText(locale==='en'?/comparison is partial/:/比較只涵蓋部分選項/);
    await partial.waitFor();
    const expectedTime=await page.evaluate(seconds=>MhkI18n.date(seconds),predictedAt);
    const prediction=panel.getByText(locale==='en'?/First future prediction/:/最早未來預測/);
    await prediction.waitFor();
    assert.ok((await prediction.innerText()).includes(expectedTime));
    assert.equal(requests.filter(r=>r.body?.includeArrivals).length,1);
    await panel.getByText(locale==='en'?/returned no predictions/:/未有回傳到站預測/).waitFor();
    await panel.getByText(/SOURCE_RESTRICTED/).waitFor();
    await panel.getByText(/comparison_deadline/).waitFor();
    await panel.getByText(/STALE_SOURCE/).waitFor();
    await panel.getByText(locale==='en'?/^The prediction check has expired/:/^到站預測檢查已過期/).first().waitFor();
    await panel.getByText(locale==='en'?/past its check interval/:/已過檢查週期/).waitFor();
    timedOut=true;
    await check.press('Enter');
    await panel.getByText(locale==='en'?/^A check reached its time limit/:/^檢查已達時間上限/).waitFor();
    assert.equal(await panel.getByText(locale==='en'?/Showing 1 of 6 reference/:/顯示 1 個參考選項，共 6 個/).isVisible(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.locator('[data-family="catalogue"]').click();
    assert.equal(await panel.isVisible(),false);
    assert.deepEqual(errors,[]);
    await context.close();
  }
  console.log('Transport lookups passed at 390px and 1280px in both site locales.');
}finally{await browser.close();}
