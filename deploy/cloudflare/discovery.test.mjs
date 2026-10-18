import assert from 'node:assert/strict';
import {test} from 'node:test';
import {discoveryTarget, publicPaths} from './discovery.ts';

test('edge public pages select the exact pre-rendered locale without backend access', () => {
  for (const path of publicPaths) {
    const en = discoveryTarget(new URL('https://mcp.hk' + path));
    const zh = discoveryTarget(new URL('https://mcp.hk' + path + '?lang=zh-Hant'));
    assert.match(en.asset, /^\/discovery\/en\/.+\.html$/);
    assert.match(zh.asset, /^\/discovery\/zh-Hant\/.+\.html$/);
    assert.equal(discoveryTarget(new URL('https://mcp.hk' + path + '?lang=zh-HK')).asset, zh.asset);
  }
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/unknown')), {});
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/api/v1/catalogue/datasets')), {});
});
test('filtered discovery is noindex while tracking parameters retain canonical content', () => {
  for (const suffix of ['?q=private', '?access=all', '?offset=20', '?lang=zh-Hant&q=weather']) {
    const result = discoveryTarget(new URL('https://mcp.hk/coverage' + suffix));
    assert.equal(result.noindex, true); assert.match(result.asset, /-filtered\.html$/);
  }
  assert.equal(discoveryTarget(new URL('https://mcp.hk/coverage?utm_source=search')).noindex, false);
  assert.equal(discoveryTarget(new URL('https://mcp.hk/terms')).noindex, true);
});
test('aliases redirect once and discovery documents stay outside the query backend', () => {
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/data?lang=zh-Hant&q=weather')), {redirect:'/coverage?lang=zh-Hant&q=weather'});
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/connect/')), {redirect:'/connect'});
  for (const path of ['/robots.txt', '/sitemap.xml', '/llms.txt']) assert.deepEqual(discoveryTarget(new URL('https://mcp.hk' + path)), {asset:path});
});
