import assert from 'node:assert/strict';
import {test} from 'node:test';
import {maintenanceResponse, maintenanceRuntimeReady, EXPECTED_REVIEW_POLICY} from './maintenance.ts';
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
