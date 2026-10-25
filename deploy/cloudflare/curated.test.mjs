import test from 'node:test';
import assert from 'node:assert/strict';
import {curatedContainerEnv} from './curated.ts';
test('curated backend is optional and never substitutes the operations credential',()=>{
  assert.deepEqual(curatedContainerEnv({OPS_TOKEN:'operations-only'},'https://archive.example'),{MCP_HK_CURATED_ORIGIN:'',MCP_HK_CURATED_TOKEN:''});
  assert.equal(curatedContainerEnv({CURATED_BACKEND_TOKEN:'x'.repeat(32)},'https://archive.example').MCP_HK_CURATED_TOKEN,'x'.repeat(32));
});
test('curated origin is HTTPS only with no path, credentials or caller redirection',()=>{
  for(const origin of ['http://archive.example','https://user:password@archive.example','https://archive.example/path','https://archive.example?destination=elsewhere','https://archive.example:1234']){
    assert.equal(curatedContainerEnv({CURATED_BACKEND_TOKEN:'x'.repeat(32)},origin).MCP_HK_CURATED_ORIGIN,'');
  }
});
test('the Webb archive consumer requires explicit activation and a configured backend',()=>{
  const env={CURATED_BACKEND_TOKEN:'x'.repeat(32)};
  assert.equal(curatedContainerEnv(env,'https://archive.example').MCP_HK_WEBB_SDI_ENABLED,undefined);
  assert.equal(curatedContainerEnv({...env,WEBB_SDI_ARCHIVE_ENABLED:'true'},'https://archive.example').MCP_HK_WEBB_SDI_ENABLED,'true');
  assert.equal(curatedContainerEnv({...env,WEBB_SDI_ARCHIVE_ENABLED:'false'},'https://archive.example').MCP_HK_WEBB_SDI_ENABLED,undefined);
  assert.equal(curatedContainerEnv({WEBB_SDI_ARCHIVE_ENABLED:'true'},'https://archive.example').MCP_HK_WEBB_SDI_ENABLED,undefined);
});
