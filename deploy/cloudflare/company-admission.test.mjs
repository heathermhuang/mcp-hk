import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Admission} from './company-admission.mjs';
test('browser and next process honor persisted quota headroom and Retry-After',async()=>{
 const folder=await mkdtemp(join(tmpdir(),'company-admission-'));let now=100000;const waits=[];const options={now:()=>now,sleep:async ms=>{waits.push(ms);now+=ms;}};
 try{const path=join(folder,'admission.json');let gate=new Admission(path,options);await gate.before();await gate.observe(200,{'RateLimit-Remaining':'1','RateLimit-Reset':'30'});gate=new Admission(path,options);await gate.before();assert.equal(now,130000);assert.deepEqual(waits,[30000]);await gate.observe(429,{'Retry-After':'15'});gate=new Admission(path,options);await gate.before();assert.equal(now,145000);await gate.observe(429,{'Retry-After':'86400'});await assert.rejects(gate.before(),/QUOTA_DEFERRED/);assert.equal(JSON.parse(await readFile(path,'utf8')).notBeforeMs,86545000);}
 finally{await rm(folder,{recursive:true});}
});
