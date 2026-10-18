import assert from 'node:assert/strict';
import {test} from 'node:test';
import {maintenanceResponse, maintenanceRuntimeReady, EXPECTED_REVIEW_POLICY, scheduledMaintenance} from './maintenance.ts';
import {readFileSync} from 'node:fs';
import {safeOperationError} from './backup.ts';
const redact=error=>safeOperationError(error,'test-token');

test('a held lease reports 409 and its deadline without clearing or restarting anything',async()=>{
  let calls=0;
  const app={async maintain(){calls++;throw Error('Maintenance already running');},async operationDiagnostics(){return {leaseUntil:125000};}};
  const r=await maintenanceResponse(app,'resources',redact,100000);
  assert.equal(r.status,409);assert.equal(r.headers.get('Retry-After'),'25');assert.equal((await r.json()).error.code,'MAINTENANCE_BUSY');assert.equal(calls,1);
});
test('failed operations are structured and redact credentials; success receipts remain intact',async()=>{
  const app={async maintain(){throw Error('failed test-token Bearer another-token');},async operationDiagnostics(){return {leaseUntil:null};}};
  const r=await maintenanceResponse(app,'backup',redact);assert.equal(r.status,503);const body=await r.text();assert.doesNotMatch(body,/test-token|another-token/);assert.match(body,/MAINTENANCE_FAILED/);
  const success=await maintenanceResponse({...app,async maintain(){return {sha256:'accepted-checkpoint'};}},'backup',redact);assert.equal(success.status,200);assert.equal((await success.json()).sha256,'accepted-checkpoint');
});

test('maintenance requires the matching runtime policy and the Python/Worker contract stays aligned',()=>{
  assert.equal(maintenanceRuntimeReady({status:'ok',sourceReviewPolicy:EXPECTED_REVIEW_POLICY}),true);
  assert.equal(maintenanceRuntimeReady({status:'ok',sourceReviewPolicy:'source-review-1'}),false);
  assert.equal(maintenanceRuntimeReady(null),false);
  const source=readFileSync(new URL('../../src/mcp_open_data_hk/quality.py',import.meta.url),'utf8');
  assert.equal(source.match(/REVISION = "([^"]+)"/)[1],EXPECTED_REVIEW_POLICY);
});
test('an image still rolling out is reported as recovering rather than claiming a busy lease',async()=>{
  const app={async maintain(){throw Error('DATA_RUNTIME_NOT_READY');},async operationDiagnostics(){throw Error('must not be needed');}};
  const response=await maintenanceResponse(app,'resources',redact);assert.equal(response.status,503);assert.equal((await response.json()).error.code,'SERVICE_RECOVERING');assert.equal(response.headers.get('Retry-After'),'30');
});

test('scheduled cold readiness retries are bounded and preserve the eventual receipt', async()=>{
  let calls=0;const delays=[];
  const result=await scheduledMaintenance({async maintain(){if(++calls<3)throw Error('DATA_RUNTIME_NOT_READY');return {sha256:'accepted'};}},'resources',async ms=>{delays.push(ms);});
  assert.equal(calls,3);assert.deepEqual(delays,[30000,30000]);assert.equal(result.sha256,'accepted');
  calls=0;await assert.rejects(scheduledMaintenance({async maintain(){calls++;throw Error('DATA_RUNTIME_NOT_READY');}},'resources',async()=>{}),/DATA_RUNTIME_NOT_READY/);assert.equal(calls,3);
});
test('scheduled maintenance never retries a held lease or a source/checkpoint failure',async()=>{
  for(const message of ['Maintenance already running','Maintenance failed; previous backup retained']){
    let calls=0;await assert.rejects(scheduledMaintenance({async maintain(){calls++;throw Error(message);}},'resources',async()=>{throw Error('must not wait');}));assert.equal(calls,1);
  }
});
test('idle timeout spans at least two review periods to avoid cold restore on every cron',()=>{
  const source=readFileSync(new URL('./worker.ts',import.meta.url),'utf8');const minutes=Number(source.match(/sleepAfter = '(\d+)m'/)[1]);
  const config=readFileSync(new URL('../../src/mcp_open_data_hk/review_config.py',import.meta.url),'utf8');const period=Number(config.match(/SCHEDULE_SECONDS = (\d+)/)[1]);assert.ok(minutes*60>=period*2);
});
