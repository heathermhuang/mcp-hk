/* Synthetic accepted-reader data. This validates UX, never provider qualification. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8793';
const out=new URL('../../playwright-artifacts/unified-records/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const envelope=(data,version='archive-v1',view='archive',nextCursor=null)=>({data:Array.isArray(data)?{items:data}:data,meta:{version,view,groupBy:'organisation',nextCursor},provenance:[],warnings:[]});
const official='official-'+'b'.repeat(32),sfc='sfc-'+'c'.repeat(32),webb='webb-sdi-fixture',daily='hkex-daily-'+'a'.repeat(32);
const company={entity_id:1,kind:'organisation',name1:'SAME NAME LIMITED',chinese_name:'同名有限公司',identifiers:[{namespace:'sfc:ce_reference',value:'ABC123'}],inc_raw:'2000-01-01',inc_precision:'day'};
const current={entity_id:'cr:local:00000001',name1:'SAME NAME LIMITED',identifier:{namespace:'cr:local:brn',value:'00000001'},observations:[{name1:'SAME NAME LIMITED',coverageEnd:'2026-10-18',events:[{type:'registration',dateRaw:'2026-10-01',precision:'day'}],source:{sourceUrl:'https://data.gov.hk/',fetchedAt:'2026-10-19'}}]};
const archiveFiling={id:'webb:sdi:1',serial:'DA20201001E00123',issuer_id:'webb:person:1',issuer_name:'EARLIER ISSUER',stock_code:'00005',discloser:{name1:'ARCHIVE DIRECTOR'},event_date:'2020-10-01',before:{long_shares:'12'},after:{long_shares:'15'},revision_links:[],capacities:[],events:[]};
const summary={id:'hkex:daily:1',serial:'DA20261027E00123',issuer_name:'LATER ISSUER',stock_code:'00005',discloser:'NEWER DIRECTOR',event_date:'2026-10-26',summary_date:'2026-10-27',filed_date:null,form:'3A',interests:[],revision:{}};
const licence={ce:'ABC123',nameEn:'SAME NAME LIMITED',observedAt:'2026-10-27T00:00:00Z',sourceCutoff:{raw:null,precision:'unknown'},activities:[{label:'Dealing in securities',statusLabel:'Source active',start:{raw:'2000-01',precision:'month'},end:{raw:null,precision:'unknown'}}]};
let errors=[];const receipts=[];
try{for(const width of [320,390,768,1280])for(const lang of ['en','zh-Hant']){
 const context=await browser.newContext({viewport:{width,height:900},colorScheme:'dark'}),page=await context.newPage();let failOfficial=false,archiveCalls=0;const calls=[];
 page.on('pageerror',e=>errors.push(e.message));await context.route('https://hk.app/**',r=>r.abort());
 await context.route('**/api/v1/**',async route=>{const u=new URL(route.request().url()),p=u.pathname,q=u.searchParams;calls.push(p+u.search);let body,status=200;
 if(p.endsWith('/notice'))return route.fulfill({contentType:'text/plain',body:p.includes('/latest/')?'Source: Hong Kong Exchanges and Clearing Limited (HKEX).':'David Webb / Webb-site'});
 if(p==='/api/v1/companies'){
  const isOfficial=q.get('view')==='latest_observed';if(!isOfficial)assert.equal(q.has('version'),false,'Archive search uses its signed cursor, not an explicit version parameter');if(isOfficial&&failOfficial){status=503;body={error:{code:'PACK_UNAVAILABLE'}};}
  else if(isOfficial)body=envelope([current],official,'latest_observed');
  else{archiveCalls++;body=envelope([{...company,entity_id:q.has('cursor')?2:1}],undefined,undefined,q.has('namespace')||q.has('cursor')?null:'next-archive');}
 }else if(p==='/api/v1/companies/updates/status')body={data:{coverage:{}}};
 else if(p==='/api/v1/companies/cr%3Alocal%3A00000001'||p==='/api/v1/companies/cr:local:00000001')body=envelope(current,official,'latest_observed');
 else if(p.match(/\/companies\/[12]$/))body=envelope({...company,entity_id:Number(p.split('/').at(-1))});
 else if(p.endsWith('/licences'))body=envelope([{company_id:1,activity_label:'Dealing in securities',start_raw:'2000-01-01',start_precision:'day'}]);
 else if(p.endsWith('/names'))body=envelope([{display_name:'EARLIER NAME',until_raw:'2000-01-01',until_precision:'day'}]);
 else if(p==='/api/v1/hkex/latest/disclosures')body=envelope([summary],daily,'hkex_daily_summary');
 else if(p.startsWith('/api/v1/hkex/latest/disclosures/'))body=envelope(summary,daily,'hkex_daily_summary');
 else if(p==='/api/v1/hkex/archive/issuers')body=envelope([{issuer_id:'webb:person:1',name:'EARLIER ISSUER',first_event:'2000-01-01',last_event:'2020-10-01'},{issuer_id:'webb:person:2',name:'DIFFERENT ISSUER',first_event:'1990-01-01',last_event:'1999-01-01'}],webb,'webb_sdi_archive');
 else if(p==='/api/v1/hkex/archive/disclosures')body=envelope([archiveFiling],webb,'webb_sdi_archive');
 else if(p.startsWith('/api/v1/hkex/archive/disclosures/'))body=envelope(archiveFiling,webb,'webb_sdi_archive');
 else if(p==='/api/v1/sfc/status')body={data:{acceptedVersion:sfc,enabledModes:['rest','browser'],historyAvailable:true}};
 else if(p==='/api/v1/sfc/corporations/ABC123')body=envelope(licence,sfc,'sfc_observation');
 else if(p==='/api/v1/sfc/corporations/ABC123/history')body={data:[{ce:'ABC123',version:sfc,observedAt:licence.observedAt}],meta:{version:sfc,nextCursor:null}};
 else if(p==='/api/v1/racing/status')body={data:{meetings:[]}};
 else{status=503;body={error:{code:'PACK_UNAVAILABLE'}};}
 return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto(origin+'/companies?lang='+lang);assert.equal(await page.locator('#record-sources').getAttribute('open'),null);assert.equal(calls.filter(path=>!path.startsWith('/api/v1/companies/updates/status')).length,0,'only accepted-state metadata before a query');
 await page.locator('#record-query').fill('SAME');await page.locator('#record-search button').click();await page.locator('.mhk-record-row').nth(1).waitFor();assert.equal(await page.locator('.mhk-record-row').count(),2,'same names are separate identities');
 await page.locator('.mhk-record-title').first().click();await page.locator('#record-content details summary').first().waitFor();assert.equal(await page.locator('#record-detail-heading').evaluate(e=>e===document.activeElement),true);
 const download=page.waitForEvent('download');await page.locator('#record-content button').filter({hasText:lang==='en'?'Download selected':'下載所選'}).click();assert.ok(await (await download).path());
 await page.locator('#record-next').click();await page.waitForFunction(()=>document.querySelector('#record-page').textContent.includes('2'));assert.equal(await page.locator('.mhk-record-row').count(),1,'exhausted source is not repeated');
 await page.reload();await page.waitForFunction(()=>document.querySelector('#record-page').textContent.includes('2'));assert.equal(await page.locator('.mhk-record-row').count(),1,'reload restores the composite page');
 await page.locator('#record-previous').click();await page.locator('.mhk-record-row').nth(1).waitFor();assert.equal(await page.locator('.mhk-record-row').count(),2);
 failOfficial=true;await page.locator('#record-search button').click();await page.locator('#record-retry').waitFor({state:'visible'});assert.equal(await page.locator('.mhk-record-row').count(),1);const before=archiveCalls;failOfficial=false;await page.locator('#record-retry').click();await page.locator('.mhk-record-row').nth(1).waitFor();assert.equal(archiveCalls,before,'retry reuses successful source');
 if(width===1280)await page.screenshot({path:new URL('companies-'+lang+'.png',out).pathname,fullPage:true});
 await page.goto(origin+'/hkex?lang='+lang);await page.locator('#record-query').fill('5');await page.locator('#record-search button').click();await page.locator('.mhk-record-row').nth(2).waitFor();assert.equal(calls.some(c=>c.includes('/archive/disclosures?')),false,'ambiguous issuers require an explicit choice');
 await page.getByRole('button',{name:'EARLIER ISSUER',exact:true}).click();await page.getByRole('button',{name:'ARCHIVE DIRECTOR',exact:true}).waitFor();assert.equal(await page.locator('.mhk-record-row').count(),2);await page.getByRole('button',{name:'ARCHIVE DIRECTOR',exact:true}).click();await page.locator('#record-content details').waitFor();assert.match(await page.locator('#record-content').innerText(),lang==='en'?/Filing date\nUnknown/:/提交日期\n未知/);
 if(width===320)await page.screenshot({path:new URL('disclosures-'+lang+'.png',out).pathname,fullPage:true});
 await page.goto(origin+'/sfc?lang='+lang);await page.locator('#record-query').fill('ABC123');await page.locator('#record-search button').click();await page.locator('.mhk-record-row').waitFor();assert.equal(await page.locator('.mhk-record-row').count(),1,'verified CE combines source variants');await page.locator('.mhk-record-title').click();await page.locator('.mhk-record-variant').nth(1).waitFor();assert.equal(await page.locator('.mhk-record-variant').count(),2);assert.match(await page.locator('#record-content').innerText(),/Dealing in securities/);
 await page.locator('.mhk-language').click();await page.locator('.mhk-record-variant').first().waitFor();assert.equal(await page.locator('#record-query').inputValue(),'ABC123');assert.equal(await page.locator('.mhk-record-variant').count(),2,'Locale restore retains both supported sources');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 if(width===320)await page.screenshot({path:new URL('licensing-'+lang+'.png',out).pathname,fullPage:true});
 await page.goto(origin+'/racing?lang='+lang);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);const style=await page.locator('#mhk-preview').evaluate(e=>({width:getComputedStyle(e).maxWidth,color:getComputedStyle(e).color}));assert.equal(style.width,'1120px');assert.equal(await page.locator('.mhk-window').evaluate(e=>getComputedStyle(e).borderTopWidth),'1px');
 if(width===320||width===1280)await page.screenshot({path:new URL('racing-'+lang+'-'+width+'.png',out).pathname,fullPage:true});
 receipts.push({width,lang,oneSearch:true,identitiesPreserved:true,independentPaging:true,partialFailureAndRetry:true,downloads:true,language:true,overflow:false});await context.close();
 }assert.deepEqual(errors,[]);await writeFile(new URL('receipt.json',out),JSON.stringify({scope:'synthetic reader UX; no source collection or provider acceptance',receipts,errors},null,2)+'\n');console.log(`Unified records: ${receipts.length} rendered journeys passed`);
}finally{await browser.close();}
