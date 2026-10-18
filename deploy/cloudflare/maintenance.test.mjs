import assert from 'node:assert/strict';
import {test} from 'node:test';
import {maintenanceResponse} from './maintenance.ts';
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
