import assert from 'node:assert/strict';
import {test} from 'node:test';
import {discoveryTarget, publicPaths, agentFiles, prefersMarkdown} from './discovery.ts';

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
  for(const suffix of ['?q=private','?provider=independent','?access=sources&offset=10','?lang=zh-Hant&q=weather']){const selected=discoveryTarget(new URL('https://mcp.hk/'+suffix));assert.equal(selected.noindex,true);assert.match(selected.asset,/-filtered\.html$/);assert.match(discoveryTarget(new URL('https://mcp.hk/'+suffix),'text/markdown').asset,/-filtered\.md$/);}
  assert.equal(discoveryTarget(new URL('https://mcp.hk/?utm_source=search')).noindex,false);
  assert.equal(discoveryTarget(new URL('https://mcp.hk/coverage?utm_source=search')).noindex, false);
  assert.equal(discoveryTarget(new URL('https://mcp.hk/terms')).noindex, true);
});
test('aliases redirect once and discovery documents stay outside the query backend', () => {
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/data?lang=zh-Hant&q=weather')), {redirect:'/coverage?lang=zh-Hant&q=weather'});
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/connect/')), {redirect:'/connect'});
  for (const path of ['/robots.txt', '/sitemap.xml', '/llms.txt']) assert.deepEqual(discoveryTarget(new URL('https://mcp.hk' + path)), {asset:path});
});

test('Markdown negotiation respects quality and never changes the browser default',()=>{
  const vectors=[['',false],['*/*',false],['text/html,application/xhtml+xml,*/*;q=0.8',false],['text/markdown',true],['TEXT/MARKDOWN; charset=utf-8',true],['text/markdown;q=0,*/*;q=1',false],['text/markdown;q=0.4,text/html;q=1',false],['text/html;q=0.4,text/markdown;q=1',true],['text/*;q=1,text/markdown;q=0.5',false],['text/markdown;q=1,text/html;q=1',true],['text/markdown;q=bogus',false]];
  for(const [accept,expected] of vectors){
    assert.equal(prefersMarkdown(accept),expected,accept);
    const selected=discoveryTarget(new URL('https://mcp.hk/?lang=zh-Hant'),accept);
    assert.equal(selected.contentType,expected?'text/markdown':'text/html');assert.equal(selected.language,'zh-Hant');
    assert.match(selected.asset,expected?/\.md$/:/\.html$/);
  }
  assert.equal(discoveryTarget(new URL('https://mcp.hk/connect.md')).noindex,true);
  assert.equal(discoveryTarget(new URL('https://mcp.hk/privacy'),'text/markdown').contentType,'text/html');
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/unknown.md')),{});
});
test('agent discovery documents use only fixed static asset routes and correct media types',()=>{
  for(const [path,file] of Object.entries(agentFiles)) {
    const selected=discoveryTarget(new URL('https://mcp.hk'+path));
    assert.equal(selected.asset,file.asset);assert.equal(selected.contentType,file.contentType);
    assert.match(selected.asset,/^\/discovery\/agents\//);
  }
  assert.equal(discoveryTarget(new URL('https://mcp.hk/.well-known/api-catalog')).contentType,'application/linkset+json');
  assert.deepEqual(discoveryTarget(new URL('https://mcp.hk/.well-known/oauth-authorization-server')),{});
});

test('company selection URLs are noindex in both locale assets and preserve canonical explorer routes',()=>{
 for(const suffix of ['?q=香港','?entity=341&version=archive-v1','?namespace=webb:person&value=341']){
  const selected=discoveryTarget(new URL('https://mcp.hk/companies'+suffix));assert.equal(selected.noindex,true);assert.match(selected.asset,/-filtered\.html$/);
 }
 assert.equal(discoveryTarget(new URL('https://mcp.hk/companies?lang=zh-Hant')).noindex,false);
});

test('integrated disclosure and licensing selections are noindex in both locales',()=>{
 for(const route of ['/hkex','/sfc'])for(const lang of ['en','zh-Hant']){
  const selected=discoveryTarget(new URL(`https://mcp.hk${route}?lang=${lang}&q=ABC123&record=source:1`));
  assert.equal(selected.noindex,true);assert.match(selected.asset,/-filtered\.html$/);
  assert.equal(discoveryTarget(new URL(`https://mcp.hk${route}?lang=${lang}`)).noindex,false);
 }
});
