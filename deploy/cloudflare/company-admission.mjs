/* Shared operator pacing only. Never raises or clears the public allowance. */
import {readFile,writeFile,rename,mkdir} from 'node:fs/promises';
import {dirname} from 'node:path';
export class Admission {
 constructor(path,{now=()=>Date.now(),sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){this.path=path;this.now=now;this.sleep=sleep;}
 async read(){try{return JSON.parse(await readFile(this.path,'utf8'));}catch(e){if(e.code==='ENOENT')return {};throw e;}}
 async save(value){await mkdir(dirname(this.path),{recursive:true,mode:0o700});await writeFile(this.path+'.tmp',JSON.stringify(value),{mode:0o600});await rename(this.path+'.tmp',this.path);}
 async before(){const state=await this.read();const delay=Math.max((state.lastDispatchMs||0)+2100,state.notBeforeMs||0)-this.now();if(delay>60000)throw Error('ACCEPTANCE_QUOTA_DEFERRED');if(delay>0)await this.sleep(delay);await this.save({...state,lastDispatchMs:this.now()});}
 async observe(status,headers){const state=await this.read(),now=this.now();headers=Object.fromEntries(Object.entries(headers).map(([k,v])=>[k.toLowerCase(),v]));const number=k=>/^\d+$/.test(headers[k]||'')?Math.min(86400,Number(headers[k])):null;let seconds=0;if(number('ratelimit-remaining')!==null&&number('ratelimit-remaining')<=10)seconds=number('ratelimit-reset')||0;if(status===429)seconds=Math.max(seconds,number('retry-after')??60);if(seconds)state.notBeforeMs=Math.max(state.notBeforeMs||0,now+seconds*1000);await this.save(state);}
}
