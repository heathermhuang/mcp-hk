/* Documentation UX only: source records are never queried by page load or search. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:8765';
const out=new URL('../../playwright-artifacts/docs/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});const receipts=[],errors=[];
try{
 for(const width of [320,390,768,1280])for(const lang of ['en','zh-Hant']){
  const context=await browser.newContext({viewport:{width,height:900},permissions:['clipboard-read','clipboard-write']}),page=await context.newPage(),calls=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>calls.push(new URL(r.url()).pathname));
  await page.goto(origin+'/docs?lang='+lang);await page.waitForFunction(()=>!document.querySelector('#docs-query').disabled);
  const count=await page.locator('.docs-operation').count();assert.ok(count>=40);assert.equal(await page.locator('.docs-group[open]').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.equal(calls.includes('/assets/swagger-ui-bundle.js'),false);assert.equal(calls.some(p=>p.startsWith('/api/v1/')),false);
  await page.locator('#docs-copy').click();assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),await page.locator('#docs-first-code').innerText());
  await page.locator('#docs-query').fill(lang==='en'?'population':'人口');await page.locator('#docs-query').press('Enter');assert.equal(await page.locator('.docs-operation').count(),2);
  const summary=page.locator('.docs-operation').filter({has:page.locator('summary code',{hasText:'/api/v1/districts/{districtId}/statistics'})}).locator(':scope>summary');await summary.focus();await page.keyboard.press('Enter');assert.equal(await page.locator('.docs-operation[open]').count(),1);assert.ok((await page.locator('.docs-operation[open]').innerText()).includes('districtId'));
  await page.locator('.mhk-language').click();await page.waitForFunction(()=>!document.querySelector('#docs-query').disabled);assert.equal(new URL(page.url()).searchParams.get('q'),lang==='en'?'population':'人口');assert.equal(await page.locator('.docs-operation[open]').count(),1);
  await page.locator('.mhk-language').click();await page.waitForFunction(()=>!document.querySelector('#docs-query').disabled);
  await page.locator('#docs-clear').click();await page.locator('#docs-group').selectOption('racing');assert.ok(await page.locator('.docs-operation').count());assert.equal(await page.locator('.docs-group').count(),1);
  await page.locator('#docs-query').fill('GET /api/v1/racing/races');await page.locator('#docs-query').press('Enter');assert.equal(await page.locator('.docs-operation').count(),2);
  await page.locator('#docs-query').fill('no-such-endpoint-20261029');await page.locator('#docs-query').press('Enter');assert.equal(await page.locator('.docs-operation').count(),0);
  await page.locator('#docs-clear').click();assert.equal(await page.locator('.docs-operation').count(),count);
  await page.locator('#docs-query').fill('GET /api/v1/resources');await page.locator('#docs-query').press('Enter');assert.equal(await page.locator('.docs-operation').count(),3);
  await page.locator('#docs-query').fill('POST /api/v1/resources');await page.locator('#docs-query').press('Enter');
  const resource=page.locator('.docs-operation').filter({has:page.locator('summary code',{hasText:'/api/v1/resources/{resourceId}/query'})});await resource.locator(':scope>summary').click();assert.ok((await resource.innerText()).includes('recordPath'));assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  if([390,1280].includes(width)){await page.locator('#api-reference').scrollIntoViewIfNeeded();await page.screenshot({path:new URL(`reference-${lang}-${width}.png`,out).pathname});}
  await page.locator('#docs-clear').click();
  await page.locator('#docs-console>summary').click();await page.locator('#swagger-ui .swagger-ui').waitFor();assert.equal(calls.some(p=>p.startsWith('/api/v1/')),false);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.locator('#docs-console>summary').click();
  await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:new URL(`docs-${lang}-${width}.png`,out).pathname,fullPage:true});await page.screenshot({path:new URL(`docs-top-${lang}-${width}.png`,out).pathname});
  receipts.push({width,lang,operations:count,copy:true,bilingualSearch:true,pathMethodSearch:true,groupFilter:true,keyboard:true,languageAndSelectionState:true,emptyAndReset:true,lazySwagger:true,noSourceReads:true,overflow:false});await context.close();
 }
 // A failed schema is an explicit error with recovery; the first request remains usable.
 const context=await browser.newContext(),page=await context.newPage();let fail=true;
 await page.route('**/openapi.json',route=>fail?route.fulfill({status:503,json:{error:'fixture unavailable'}}):route.continue());await page.goto(origin+'/docs?lang=zh-Hant');await page.locator('#docs-retry').waitFor();assert.ok(await page.locator('#docs-first-code').isVisible());assert.equal(await page.locator('#docs-query').isDisabled(),true);fail=false;await page.locator('#docs-retry').click();await page.waitForFunction(()=>!document.querySelector('#docs-query').disabled);assert.ok(await page.locator('.docs-operation').count());await context.close();
 // Saved locale and original Swagger links still work.
 const saved=await browser.newContext();await saved.addInitScript(()=>localStorage.setItem('mhk-language','zh'));const savedPage=await saved.newPage();savedPage.on('pageerror',e=>errors.push(e.message));await savedPage.goto(origin+'/docs');await savedPage.waitForURL('**/docs?lang=zh-Hant');await savedPage.waitForFunction(()=>!document.querySelector('#docs-query').disabled);await saved.close();
 const legacy=await browser.newContext(),legacyPage=await legacy.newPage();const schema=await (await legacyPage.request.get(origin+'/openapi.json')).json();const operation=schema.paths['/api/v1/catalogue/datasets'].get;await legacyPage.goto(origin+'/docs?lang=en#/'+encodeURIComponent(operation.tags[0])+'/'+operation.operationId);await legacyPage.locator('#swagger-ui .opblock.is-open').waitFor();await legacy.close();
 // Future operations are visible even without a hand-authored label; source text is inert.
 const future=await browser.newContext(),futurePage=await future.newPage();await futurePage.route('**/openapi.json',async route=>{const response=await route.fetch(),data=await response.json();data.paths['/api/v1/future-subject']={get:{summary:'<img src=x onerror=alert(1)>',responses:{200:{description:'Fixture'}}}};await route.fulfill({json:data});});await futurePage.goto(origin+'/docs?lang=en&q=future-subject');await futurePage.waitForFunction(()=>!document.querySelector('#docs-query').disabled);assert.equal(await futurePage.locator('.docs-operation').count(),1);assert.equal(await futurePage.locator('.docs-operation img').count(),0);await future.close();
 const consoleContext=await browser.newContext(),consolePage=await consoleContext.newPage();let cssFailure=true;await consolePage.route('**/swagger-ui.css',route=>cssFailure?route.fulfill({status:503,body:'Fixture unavailable'}):route.continue());await consolePage.goto(origin+'/docs?lang=zh-Hant');await consolePage.waitForFunction(()=>!document.querySelector('#docs-query').disabled);await consolePage.locator('#docs-console>summary').click();await consolePage.locator('#swagger-ui>button').waitFor();cssFailure=false;await consolePage.locator('#swagger-ui>button').click();await consolePage.locator('#swagger-ui .swagger-ui').waitFor();await consoleContext.close();
 assert.deepEqual(errors,[]);await writeFile(new URL('receipt.json',out),JSON.stringify({origin,receipts,schemaFailureRecovery:true,consoleFailureRecovery:true,legacyLinks:true,futureOperations:true,errors},null,2)+'\n');console.log(JSON.stringify({cases:receipts.length,schemaFailureRecovery:true,consoleFailureRecovery:true,legacyLinks:true,futureOperations:true,errors}));
}finally{await browser.close();}
