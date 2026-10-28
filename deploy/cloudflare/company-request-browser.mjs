/* Real local browser lifecycle regression; never production acceptance evidence. */
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import assert from 'node:assert/strict';
import {observeRequest} from './company-request.mjs';
const server=createServer((req,res)=>{
 if(req.url==='/slow')return;
 if(req.url==='/quota'){res.writeHead(429,{'Retry-After':'17','Content-Type':'application/json'});res.end('{"error":{"code":"RATE_LIMITED","scope":"client_minute"}}');return;}
 res.end('<html><body>Local lifecycle regression</body></html>');
});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});const page=await browser.newPage();const observations=[];const admissions=[];const handled=[],completions=[];const nextObservation=()=>new Promise(resolve=>completions.push(resolve));
await page.route('**/*',route=>{if(!['/slow','/quota'].includes(new URL(route.request().url()).pathname))return route.continue();const work=observeRequest(route,{observe:async(...args)=>admissions.push(args)},{timeout:500}).then(result=>{observations.push(result);completions.shift()?.(result);});handled.push(work);return work;});
try{
 await page.goto('http://127.0.0.1:'+server.address().port);
 let completion=nextObservation();await page.evaluate(async()=>{const controller=new AbortController();setTimeout(()=>controller.abort(),50);await fetch('/slow',{signal:controller.signal}).catch(()=>{});});await completion;
 assert.equal(observations[0].failure.kind,'network');assert.match(observations[0].failure.errorText,/ERR_ABORTED|CANCELLED/);assert.equal(admissions.length,0);
 completion=nextObservation();await page.evaluate(()=>fetch('/quota').then(r=>r.text()));await completion;assert.equal(observations[1].failure.status,429);assert.equal(observations[1].failure.headers['retry-after'],'17');assert.equal(JSON.parse(observations[1].failure.body).error.scope,'client_minute');assert.equal(admissions[0][0],429);
 // A genuinely unresolved request also terminates as unknown/deadline, never pass.
 completion=nextObservation();await page.evaluate(()=>{window.unresolved=fetch('/slow').catch(()=>{});});await completion;assert.equal(observations[2].failure.kind,'deadline');
 console.log('Actual local browser cancellation, HTTP failure and unresolved-request bounds passed; not live acceptance.');
}finally{await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
