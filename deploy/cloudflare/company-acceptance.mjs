/* Actual visible-browser acceptance only. Never mock source/API responses. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {Admission} from './company-admission.mjs';
import {observeRequest} from './company-request.mjs';
const [input,output]=process.argv.slice(2);
const task=JSON.parse(await readFile(input,'utf8'));
assert.match(task.version,/^official-[a-f0-9]{32}$/);
assert.ok(['en','zh-Hant'].includes(task.language));
const expected=task.case.expected,entity=expected.entity_id;
assert.match(entity,/^cr:(local|foreign):[0-9]+$/);
await mkdir(output,{recursive:true,mode:0o700});
const browser=await chromium.launch({headless:false,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const context=await browser.newContext({viewport:{width:1280,height:900},acceptDownloads:true});
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
const admission=new Admission(join(output,'..','..','admission.json'));let tail=Promise.resolve(),admissionFailure=null,failureResolve;const failureSignal=new Promise(resolve=>{failureResolve=resolve;});
await context.route('**/*',async route=>{
 const u=new URL(route.request().url());
 if(u.protocol==='blob:'||u.origin==='https://mcp.hk'){
  if(u.pathname.startsWith('/api/')||u.pathname.startsWith('/downloads/')){
   const next=tail.then(async()=>{
    if(admissionFailure){await route.abort();return;}
    try{await admission.before();}catch(e){admissionFailure={code:e.message};await writeFile(join(output,'admission-failure.json'),JSON.stringify(admissionFailure));failureResolve(admissionFailure);await route.abort();return;}
    const outcome=await observeRequest(route,admission);
    if(outcome.failure){admissionFailure=outcome.failure;await writeFile(join(output,'http-failure.json'),JSON.stringify(admissionFailure,null,2)+'\n');failureResolve(admissionFailure);}
   });tail=next.catch(()=>{});return next;
  }
  return route.continue();
 }
 return route.abort();
});
try{
 const query=new URLSearchParams({companySource:'official',namespace:expected.identifier.namespace,value:expected.identifier.value,official_entity:entity,official_version:task.version,lang:task.language});
 const detailResponse=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/companies/'+encodeURIComponent(entity)||decodeURIComponent(new URL(r.url()).pathname)==='/api/v1/companies/'+entity,{timeout:90000});
 // Observe rejection immediately, then await the same promise below after navigation.
 detailResponse.catch(()=>{});
 await page.goto('https://mcp.hk/companies?'+query,{timeout:90000});
 const response=await Promise.race([detailResponse,failureSignal.then(()=>{throw Error('BROWSER_REQUEST_FAILED');})]);
 assert.equal(response.status(),200);
 const envelope=await response.json();assert.equal(envelope.meta.version,task.version);assert.equal(envelope.meta.view,'latest_observed');
 assert.deepEqual(envelope.data.observations.find(r=>r.fact_id===expected.fact_id),expected);
 await page.locator('#official-detail h3').waitFor({state:'visible',timeout:90000});
 const text=await page.locator('#official-detail').innerText();assert.ok(text.includes(entity)&&text.includes(task.version));
 assert.equal(await page.locator('html').getAttribute('lang'),task.language);
 const raw=page.locator('#official-detail details').filter({has:page.locator('pre').filter({hasText:expected.fact_id})});
 assert.equal(await raw.count(),1);await raw.locator('summary').click();
 assert.deepEqual(JSON.parse(await raw.locator('pre').innerText()),expected);
 assert.equal(await raw.locator('pre').isVisible(),true);
 assert.equal(await page.locator('#official-detail a').filter({hasText:'Companies Registry'}).count()>0,true);
 const downloadEvent=page.waitForEvent('download',{timeout:60000});
 await page.locator('#official-detail-download').click();
 const download=await downloadEvent;assert.equal(await download.failure(),null);
 await download.saveAs(join(output,'actual.zip'));
 const selection={family:'official-detail',entityId:entity,version:task.version};
 const packaged={...envelope,data:{items:[envelope.data]}};
 await writeFile(join(output,'envelope.json'),JSON.stringify(packaged,null,2)+'\n');
 await writeFile(join(output,'selection.json'),JSON.stringify(selection,null,2)+'\n');
 if(task.screenshot)await page.screenshot({path:join(output,'visible.png'),fullPage:true});
 await tail;assert.equal(admissionFailure,null);assert.deepEqual(errors,[]);
 await writeFile(join(output,'receipt.json'),JSON.stringify({actualVisibleBrowser:true,downloadAction:'official-detail-download',language:task.language,version:task.version,entityId:entity,sourceKey:task.case.id,factId:expected.fact_id,downloadedAt:new Date().toISOString(),filename:download.suggestedFilename(),errors},null,2)+'\n');
}catch(error){await page.screenshot({path:join(output,'failed.png'),fullPage:true}).catch(()=>{});throw error;}
finally{await tail.catch(()=>{});await context.close();await browser.close();}
