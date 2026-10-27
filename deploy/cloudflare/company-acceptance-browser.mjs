/* Synthetic rendered regressions; never full-cohort/production acceptance. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const output=new URL('../../playwright-artifacts/company-acceptance/',import.meta.url);await mkdir(output,{recursive:true});
const version='official-'+'a'.repeat(32),id='cr:local:05243897';
const fact={fact_id:'f'.repeat(64),entity_id:id,kind:'company_event',name1:'Synthetic Company',identifier:{namespace:'cr:local:brn',value:'05243897'},names:['Synthetic Company','虛構測試公司'],events:[{type:'name_change',date:'2026-10-05',dateRaw:'05-10-2026',precision:'day'}],source:{sourceUrl:'https://www.cr.gov.hk/docs/wrpt/RNC063/RNC063L_20261005.csv',sha256:'b'.repeat(64),fetchedAt:'2026-10-27T00:00:00Z'},coverageEnd:'2026-10-11',raw:{'BR Number':'05243897'}};
const detail={data:{entity_id:id,name1:fact.name1,identifier:fact.identifier,observations:[fact,{...fact,fact_id:'e'.repeat(64)}],observationCountScope:'at_most_100_in_selected_version'},meta:{version,view:'latest_observed'},provenance:[{sourceId:'companies_registry'}],warnings:[]};
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[];
try{
 for(const language of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true}),page=await context.newPage();let searched=0;
  page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
  await context.route('**/api/v1/companies**',route=>{
   const u=new URL(route.request().url());let body;
   if(u.pathname.endsWith('/updates/status'))body={data:{coverage:{latestAcceptedCoverageEnd:'2026-10-18',moneyLenderCutoff:'2026-09-30'}}};
   else if(u.pathname==='/api/v1/companies'){
    searched++;assert.equal(u.searchParams.get('version'),version,'search itself must pin the version');assert.equal(u.searchParams.get('value'),'05243897');
    body={data:{items:[fact]},meta:{version,view:'latest_observed',groupBy:'organisation'},provenance:[],warnings:[]};
   }else if(decodeURIComponent(u.pathname)==='/api/v1/companies/'+id){assert.equal(u.searchParams.get('version'),version);body=detail;}
   else return route.abort();
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await context.route('**/downloads/companies/**',r=>r.fulfill({status:503,contentType:'application/json',body:'{}'}));
  await page.goto(origin+'/companies?'+new URLSearchParams({companySource:'official',namespace:'cr:local:brn',value:'05243897',official_entity:id,official_version:version,lang:language}));
  await page.locator('#official-detail-download').waitFor();assert.equal(searched,1);assert.match(await page.locator('#official-detail').innerText(),new RegExp(version));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  const event=page.waitForEvent('download');await page.locator('#official-detail-download').click();const download=await event;
  const dir=new URL(language+'-'+width+'/',output);await mkdir(dir,{recursive:true});await download.saveAs(new URL('actual.zip',dir).pathname);
  await writeFile(new URL('envelope.json',dir),JSON.stringify({...detail,data:{items:[detail.data]}}));
  await writeFile(new URL('selection.json',dir),JSON.stringify({family:'official-detail',entityId:id,version}));
  const verify=spawnSync(process.env.PYTHON||'python3',['-c',`from pathlib import Path
import json,sys
from mcp_open_data_hk.curated.acceptance import verify_page_zip
p=Path(sys.argv[1]);r=verify_page_zip((p/'actual.zip').read_bytes(),json.loads((p/'envelope.json').read_text()),json.loads((p/'selection.json').read_text()));assert r['rows']==1
`,dir.pathname],{env:{...process.env,PYTHONPATH:'src'},encoding:'utf8'});assert.equal(verify.status,0,verify.stderr);
  if(width===320)await page.screenshot({path:new URL('visible.png',dir).pathname,fullPage:true});
  await page.reload();await page.locator('#official-detail-download').waitFor();assert.equal(searched,2);assert.equal(new URL(page.url()).searchParams.get('official_version'),version);
  receipts.push({language,width,synthetic:true,pinnedSearch:true,actualDownloadVerified:true,fullNestedObservations:2});await context.close();
 }
 assert.deepEqual(errors,[]);await writeFile(new URL('receipts.json',output),JSON.stringify({receipts,errors},null,2)+'\n');console.log('Company acceptance: 8 rendered synthetic journeys passed');
}finally{await browser.close();}
