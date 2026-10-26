/* Real local REST and ZIP, invented source facts, zero provider traffic. */
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {inflateRawSync} from 'node:zlib';
import {createHash} from 'node:crypto';
const origin=process.env.MCP_HK_TEST_ORIGIN||'http://127.0.0.1:18765';
const output=new URL('../../playwright-artifacts/racing-profiles/',import.meta.url);await mkdir(output,{recursive:true});
function unzip(bytes){const files=new Map();let p=0;while(bytes.readUInt32LE(p)===0x04034b50){const method=bytes.readUInt16LE(p+8),size=bytes.readUInt32LE(p+18),n=bytes.readUInt16LE(p+26),extra=bytes.readUInt16LE(p+28),name=bytes.subarray(p+30,p+30+n).toString(),start=p+30+n+extra,raw=bytes.subarray(start,start+size);assert.ok([0,8].includes(method));assert.ok(!name.includes('/')&&!name.includes('..'));files.set(name,method===8?inflateRawSync(raw):raw);p=start+size;}return files;}
const browser=await chromium.launch({headless:true,...(process.env.MCP_HK_CHROME?{executablePath:process.env.MCP_HK_CHROME}:{})});
const receipts=[],errors=[],sourceRequests=[];
try{
 for(const lang of ['en','zh-Hant'])for(const width of [320,390,768,1280]){
  const context=await browser.newContext({viewport:{width,height:900},acceptDownloads:true}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  page.on('response',async response=>{if(response.url().startsWith(origin+'/api/v1/racing/')&&response.status()>=400){const body=await response.json().catch(()=>null);const failure={status:response.status(),path:new URL(response.url()).pathname,code:body?.error?.code};errors.push(failure);console.error(JSON.stringify(failure));}});
  // Exercise the real shared limiter at a sustainable request pace.
  await context.route(origin+'/api/v1/racing/**',async route=>{await new Promise(resolve=>setTimeout(resolve,1150));await route.continue();});
  await context.route(/https:\/\/[^/]*hkjc\.com\//,r=>{sourceRequests.push(r.request().url());return r.abort();});
  await context.route('https://hk.app/**',r=>r.abort());
  await page.goto(origin+'/racing?lang='+lang);await page.locator('#rows tr').waitFor();
  await page.getByRole('button',{name:lang==='en'?'TEST HORSE':'測試馬',exact:true}).first().click();
  await page.locator('#profile-download:not([hidden])').waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.match(await page.locator('#profile-dates').innerText(),/2026-10-26/);
  assert.match(await page.locator('#profile-history-scope').innerText(),lang==='en'?/not complete career/:/並非完整/);
  const pinned=new URL(page.url()).searchParams.get('profileVersion');assert.match(pinned,/^racing-profile-v1-[a-f0-9]{64}$/);
  const pending=page.waitForEvent('download');await page.locator('#profile-download').click();const downloaded=await pending,bytes=await readFile(await downloaded.path()),members=unzip(bytes),manifest=JSON.parse(members.get('manifest.json'));
  assert.equal(manifest.version,pinned);assert.equal(manifest.historyRows,2);assert.equal(manifest.scope,'profile_and_selected_history_page');
  for(const [name,entry] of Object.entries(manifest.files)){const body=members.get(name);assert.equal(body.length,entry.bytes);assert.equal(createHash('sha256').update(body).digest('hex'),entry.sha256);}
  const detail=JSON.parse(members.get('profile.json'));assert.equal(detail.data.attributes.rating.en.value,'60');assert.equal(detail.meta.currentValuesAppliedToPastRaces,false);
  if(width===320)await page.screenshot({path:new URL(lang+'-320.png',output).pathname,fullPage:true});
  await page.locator('#language').click();await page.waitForURL(u=>u.searchParams.get('lang')===(lang==='en'?'zh-Hant':'en'));await page.locator('#profile-download:not([hidden])').waitFor();assert.equal(new URL(page.url()).searchParams.get('profileVersion'),pinned);
  receipts.push({lang,width,overflow:false,pinnedVersion:pinned,actualZipSha256:createHash('sha256').update(bytes).digest('hex'),historyRows:2,restBackedFixture:true});await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(sourceRequests,[]);await writeFile(new URL('receipt.json',output),JSON.stringify({origin,scope:'local rendered API/ZIP with invented source facts; no provider acceptance claim',receipts,errors,sourceRequests},null,2));console.log(JSON.stringify({scenarios:receipts.length,actualDownloads:receipts.length,errors,sourceRequests}));
}finally{await browser.close();}
