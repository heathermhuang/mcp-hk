import test from 'node:test';
import assert from 'node:assert/strict';
import {completeRacingPublication} from './racing-publication.ts';
const version='racing-results-v1-'+'a'.repeat(64),digest='b'.repeat(64);
test('unchanged racing skips restoration and publication callbacks',async()=>{
 const receipt={sha256:digest};assert.equal(await completeRacingPublication(new Response('backup'),receipt,()=>assert.fail(),()=>assert.fail()),receipt);
});
test('invalid candidate identity cannot reach the restore or acceptance path',async()=>{
 await assert.rejects(completeRacingPublication(new Response('',{headers:{'X-Racing-Candidate':'private-results-v1-x'}}),{sha256:digest},()=>assert.fail(),()=>assert.fail()),/CANDIDATE_INVALID/);
});
test('restore failure never saves an accepted-pointer checkpoint',async()=>{
 await assert.rejects(completeRacingPublication(new Response('',{headers:{'X-Racing-Candidate':version}}),{sha256:digest},async(v,d)=>{assert.equal(v,version);assert.equal(d,digest);return new Response('failed',{status:409});},()=>assert.fail()),/RESTORE_NOT_CONFIRMED/);
});
test('successful actual-restore response is checkpointed before success is returned',async()=>{
 const calls=[];
 const result=await completeRacingPublication(new Response('',{headers:{'X-Racing-Candidate':version}}),{sha256:digest},async(v,d)=>{calls.push(['restore',v,d]);return new Response('accepted checkpoint');},async r=>{calls.push(['save',await r.text()]);return {sha256:'c'.repeat(64)};});
 assert.deepEqual(calls,[['restore',version,digest],['save','accepted checkpoint']]);assert.equal(result.sha256,'c'.repeat(64));assert.equal(result.racing.restoreCheckpointSha256,digest);
});
