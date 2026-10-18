import assert from 'node:assert/strict';
import {test} from 'node:test';
import {approvedSource,relayApprovedSource} from './source-relay.ts';
import registry from '../../src/mcp_open_data_hk/source-relay-targets.json' with {type:'json'};

const id='8e4b55c8803277a7e109d007bfac4d98';
test('approved relay targets are finite registered HTTPS government URLs',()=>{
  assert.equal(Object.keys(registry.targets).length,31);
  for(const key of Object.keys(registry.targets)){assert.ok(approvedSource(key));assert.equal(new URL(approvedSource(key)).protocol,'https:');}
  for(const key of ['__proto__','constructor','http://127.0.0.1','0'.repeat(32)])assert.equal(approvedSource(key),undefined);
});
test('relay streams exact bytes and validators without forwarding credentials or cookies',async()=>{
  const incoming=new Request('https://mcp.hk/__ops/source-relay?resourceId='+id,{headers:{Authorization:'Bearer private-token',Cookie:'private-cookie','If-None-Match':'accepted'}});
  const response=await relayApprovedSource(incoming,async(url,init)=>{
    assert.equal(url,'https://xpms.hyd.gov.hk/psi/datasets/XP_DATA.json');assert.equal(init.method,'GET');assert.equal(init.redirect,'manual');
    assert.equal(init.headers.get('Authorization'),null);assert.equal(init.headers.get('Cookie'),null);assert.equal(init.headers.get('If-None-Match'),'accepted');
    return new Response('[{"source":1}]',{headers:{ETag:'accepted','Set-Cookie':'do-not-forward','Content-Type':'application/json'}});
  });assert.equal(await response.text(),'[{"source":1}]');assert.equal(response.headers.get('Set-Cookie'),null);assert.equal(response.headers.get('ETag'),'accepted');assert.equal(response.headers.get('X-Mcp-Source-Transport'),'approved-worker-relay');
});
test('relay rejects unknown ids, non-GET and unsafe redirects',async()=>{
  let calls=0;const never=async()=>{calls++;throw Error('must not call');};
  assert.equal((await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?resourceId=__proto__'),never)).status,404);
  assert.equal((await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?resourceId='+id,{method:'POST'}),never)).status,405);assert.equal(calls,0);
  for(const location of ['http://xpms.hyd.gov.hk/insecure','https://127.0.0.1/private','https://evil.example/','https://user:pass@xpms.hyd.gov.hk/data']){
    calls=0;const response=await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?resourceId='+id),async()=>{calls++;return new Response(null,{status:302,headers:{Location:location}});});assert.equal(response.status,502);assert.equal(calls,1);
  }
});
test('same-host verified HTTPS canonical redirects retain the public-source boundary',async()=>{
  let calls=0;const response=await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?resourceId='+id),async()=>{calls++;return calls===1?new Response(null,{status:301,headers:{Location:'/psi/datasets/canonical.json'}}):new Response('[]');});assert.equal(await response.text(),'[]');assert.equal(calls,2);
});
