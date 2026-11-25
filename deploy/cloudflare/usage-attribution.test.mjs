import assert from 'node:assert/strict';
import {createHmac, randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {test} from 'node:test';
import {AttributionStore, requestAttribution} from './usage-attribution.ts';
import {describeRequest, inspectResponse} from './usage.ts';
import tools from './mcp-tool-names.json' with {type: 'json'};

const secret = 'test-only-attribution-key';
const request = headers => new Request('https://mcp.hk/mcp', {headers});
const day = 86_400_000;
const now = Date.UTC(2026, 10, 25, 3);
const installationId = randomUUID();

function marker(timestamp) {
  const issued = String(Math.floor(timestamp / 1000));
  return issued + '.' + createHmac('sha256', secret).update('mcp.hk:usage-test:v1:' + issued).digest('hex');
}

function sqlite() {
  const db = new DatabaseSync(':memory:');
  const sql = {exec(query, ...bindings) {
    const statement = db.prepare(query);
    if (!query.startsWith('SELECT')) return statement.run(...bindings);
    return {toArray: () => statement.all(...bindings), one: () => statement.get(...bindings)};
  }};
  return {db, store: new AttributionStore(sql)};
}

test('registered tool names map exactly and arbitrary labels stay unclassified', () => {
  assert.equal(new Set(tools).size, tools.length);
  for (const name of [...tools, 'user-supplied-label']) {
    const body = Buffer.from(JSON.stringify({method:'tools/call',params:{name,arguments:{query:'private phrase'}}}));
    const op = describeRequest(request({}),body);
    assert.equal(op.operation,tools.includes(name) ? name : 'unclassified_tool');
    assert.doesNotMatch(JSON.stringify(op),/private phrase|user-supplied-label/);
  }
});

test('test attribution requires a fresh signature, and opt-out suppresses identity', async () => {
  const headers = {'X-Mcp-Usage-Test':marker(now), 'X-Mcp-Usage-Installation':installationId, 'User-Agent':'codex-cli'};
  assert.deepEqual(await requestAttribution(request(headers),secret,now),
    {traffic:'operator_test',client:'codex',evidence:'user_agent',installation:null});
  const expired = await requestAttribution(request({...headers,'X-Mcp-Usage-Test':marker(now-301_000)}),secret,now);
  assert.equal(expired.traffic,'unmarked');
  assert.match(expired.installation,/^[a-f0-9]{64}$/);
  assert.notEqual(expired.installation,installationId);
  assert.equal((await requestAttribution(request(headers),'wrong secret',now)).traffic,'unmarked');
  for (const privacy of [{DNT:'1'},{'Sec-GPC':'1'},{Cookie:'__Host-mhk_analytics=off'},{'X-Mcp-Analytics-Opt-Out':'1'}]) {
    const optOut = await requestAttribution(request({...headers,'X-Mcp-Usage-Test':'1',...privacy}),secret,now);
    assert.deepEqual(optOut,{traffic:'privacy_opt_out',client:'unknown',evidence:'none',installation:null});
  }
});

test('private store reports marked traffic and returning opt-in installations without exposing hashes', async () => {
  const {db,store} = sqlite();
  const optIn = await requestAttribution(request({'X-Mcp-Usage-Installation':installationId,'X-Mcp-Usage-Client':'claude-code'}),secret,now);
  store.record('mcp','hk_property_building',optIn,'not_found',now-2*day);
  store.record('mcp','hk_property_building',optIn,'empty_result',now);
  store.record('mcp','hk_property_building',{...optIn,traffic:'operator_test',installation:null},'invalid_query',now);
  store.record('http','property_building',{...optIn,traffic:'privacy_opt_out',installation:null},'provider_timeout',now);
  const report = store.report(7,now);
  assert.equal(report.installations.distinct,1);
  assert.equal(report.installations.returning,1);
  assert.equal(report.installations.linkedCalls,2);
  assert.equal(store.report(1,now).installations.returning,0);
  assert.deepEqual(new Set(report.traffic.map(item=>item.traffic)),new Set(['unmarked','operator_test','privacy_opt_out']));
  assert.doesNotMatch(JSON.stringify(report),new RegExp(installationId+'|'+optIn.installation+'|'+secret));
  store.cleanup(now+31*day);
  assert.equal(db.prepare('SELECT count(*) AS n FROM usage_installations').get().n,0);
  assert.equal(store.report(30,now+31*day).traffic.length,0);
  db.close();
});

test('property measurement separates malformed IDs, missing buildings, provider errors and empty results', () => {
  const op = {protocol:'mcp',operation:'hk_property_building',resource:'',dataset:'',sourceCalls:0};
  const toolError = text => JSON.stringify({result:{isError:true,content:[{type:'text',text}]}});
  for (const [message,category] of [
    ['INVALID_QUERY: substitute identifier', 'invalid_query'],
    ["Error calling tool 'hk_property_building': NOT_FOUND: private payload", 'not_found'],
    ["Error calling tool 'hk_property_building': UPSTREAM_TIMEOUT: retry", 'provider_timeout'],
    ["Error calling tool 'hk_property_building': SOURCE_SCHEMA_CHANGED: schema changed", 'provider_schema_error'],
    ['ordinary application error mentions NOT_FOUND', 'error'],
  ]) {
    const fact = inspectResponse(toolError(message),op,200);
    assert.equal(fact.outcome,'error');
    assert.equal(fact.category,category);
    assert.doesNotMatch(JSON.stringify(fact),/private payload/);
  }
  const empty = inspectResponse(JSON.stringify({result:{structuredContent:{data:{listings:[]},provenance:[{sourceId:'seehouse'}]}}}),op,200);
  assert.equal(empty.outcome,'ok');
  assert.equal(empty.category,'empty_result');
});
