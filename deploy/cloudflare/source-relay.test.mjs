import assert from 'node:assert/strict';
import {test} from 'node:test';
import {approvedSource,relayApprovedSource} from './source-relay.ts';
import registry from '../../src/mcp_open_data_hk/source-relay-targets.json' with {type:'json'};

const id='8e4b55c8803277a7e109d007bfac4d98';
test('approved relay targets are finite registered HTTPS government URLs',()=>{
  assert.equal(Object.keys(registry.targets).length,34);
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

test('typed Citybus contract builds only selected public route/stop/ETA URLs',async()=>{
  const cases=[
    ['8794004d904a1b6dd40199d3a5db1778',{route:'13',direction:'outbound'},'route-stop/CTB/13/outbound'],
    ['3eca9b6a7bf3414531b1206042744a2f',{stop_id:'001042'},'stop/001042'],
    ['2b1b8d6b425bf3ddd1e1ddb811d54ba4',{stop_id:'001042',route:'13'},'eta/CTB/001042/13'],
  ];
  for(const [resourceId,args,path]of cases){
    const response=await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?'+new URLSearchParams({resourceId,...args}),{headers:{Authorization:'Bearer private-token',Cookie:'private'}}),async(url,init)=>{
      assert.equal(url,'https://rt.data.gov.hk/v2/transport/citybus/'+path);
      assert.equal(init.headers.get('Authorization'),null);assert.equal(init.headers.get('Cookie'),null);
      if(path.startsWith('eta/'))assert.equal(init.headers.get('Cache-Control'),'no-cache');
      return new Response('{"data":[{"providerFlag":"retained"}]}',{headers:{'Content-Type':'application/json'}});
    });assert.equal(response.status,200);assert.equal(await response.text(),'{"data":[{"providerFlag":"retained"}]}');
  }
});
test('typed Citybus selection rejects unknown, repeated and malformed parameters before source I/O',async()=>{
  const id='8794004d904a1b6dd40199d3a5db1778';let calls=0;const never=async()=>{calls++;throw Error('must not fetch');};
  for(const query of [
    'resourceId='+id,'resourceId='+id+'&route=13&direction=sideways',
    'resourceId='+id+'&route=13&direction=outbound&url=https://evil.example',
    'resourceId='+id+'&route=13&route=14&direction=outbound',
    'resourceId='+id+'&route=13%0A&direction=outbound',
    'resourceId='+id+'&route=%2F..%2Fadmin&direction=outbound',
  ])assert.equal((await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?'+query),never)).status,404);
  assert.equal(calls,0);
});
test('Citybus redirects and source denials stay explicit without trying another path',async()=>{
 const query=new URLSearchParams({resourceId:'8794004d904a1b6dd40199d3a5db1778',route:'13',direction:'outbound'});
 for(const status of [403,429,302]){let calls=0;const response=await relayApprovedSource(new Request('https://mcp.hk/__ops/source-relay?'+query),async()=>{calls++;return new Response('provider response',{status,headers:status===302?{Location:'https://rt.data.gov.hk/unapproved'}:{}});});assert.equal(calls,1);assert.equal(response.status,status===302?502:status);}
});
