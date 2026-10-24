/** Offline original-pin auth behavior, with synthetic credentials never logged. */
import {execFileSync} from 'node:child_process';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {DatabaseSync} from 'node:sqlite';
const ref='4692f9a4c199aaabc75e26eb837cbb918e672553',folder=await mkdtemp(join(tmpdir(),'mcp-hk-security-baseline-'));
try {
 const file=join(folder,'agent-auth.ts');await writeFile(file,execFileSync('git',['show',ref+':deploy/cloudflare/agent-auth.ts']));
 const {AgentAuthService}=await import(pathToFileURL(file));
 const db=new DatabaseSync(':memory:'),sql={exec(q,...v){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...v):(s.run(...v),[]);}};
 const service=new AgentAuthService(sql,'https://mcp.hk');await service.init();
 const form=data=>service.handle(new Request('https://mcp.hk/agent/account',{method:'POST',headers:{Origin:'https://mcp.hk','Content-Type':'application/x-www-form-urlencoded',...(data.cookie?{Cookie:data.cookie}:{})},body:new URLSearchParams(data)}));
 const created=await form({action:'create'}),html=await created.text(),cookie=created.headers.get('Set-Cookie').split(';')[0],key=html.match(/<code>(recover_[^<]+)/)[1],csrf=html.match(/name="csrf" value="([^"]+)/)[1];
 const race=await Promise.all([form({action:'login',recovery_key:key}),form({action:'login',recovery_key:key})]);
 const oldAction=await form({action:'logout',cookie,csrf});
 console.log(JSON.stringify({test:'F1-before-recovery',source:ref,recoveryStatuses:race.map(r=>r.status),oldCookieProtectedAction:oldAction.status,expected:'one winner; previous cookies denied',result:'reusable key and surviving session observed'}));
 db.close();
} finally {await rm(folder,{recursive:true,force:true});}
