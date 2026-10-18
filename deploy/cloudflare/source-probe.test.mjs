import assert from 'node:assert/strict';
import {test} from 'node:test';
import {probePublicSource} from './source-probe.ts';
import {maintenancePackForRequest} from './maintenance.ts';

test('probe cannot fetch an arbitrary URL or object prototype property',async()=>{
  let calls=0;for(const key of ['http://127.0.0.1/','__proto__','constructor','another-host']){
    const response=await probePublicSource(key,async()=>{calls++;throw Error('must not fetch');});assert.equal(response.status,404);
  }assert.equal(calls,0);
});
test('probe uses fixed verified HTTPS GET and reports source status without following redirects',async()=>{
  const response=await probePublicSource('xpms',async(url,init)=>{
    assert.equal(url,'https://xpms.hyd.gov.hk/psi/datasets/XP_DATA.json');assert.equal(init.method,'GET');assert.equal(init.redirect,'manual');assert.equal(new Headers(init.headers).get('Authorization'),null);
    return new Response('[{"id":1}]',{status:200,headers:{'Content-Type':'application/json'}});
  });const value=await response.json();assert.equal(value.sourceStatus,200);assert.equal(value.records,1);assert.equal(value.jsonKind,'array');
});
test('probe errors never expose raw exceptions or credentials',async()=>{
  const response=await probePublicSource('hko',async()=>{throw Error('Bearer private-token');});const body=await response.text();assert.doesNotMatch(body,/private-token|Bearer/);assert.match(body,/SOURCE_PROBE_FAILED/);
});
test('legacy recovery requests use short checkpointed batches instead of one long HTTP call',()=>{
  assert.equal(maintenancePackForRequest('resources-recovery'),'resources');assert.equal(maintenancePackForRequest('resources'),'resources');assert.equal(maintenancePackForRequest('restaurants'),'restaurants');assert.equal(maintenancePackForRequest('unrecognized'),'unrecognized');
});
