import assert from 'node:assert/strict';
import {test} from 'node:test';
import {scheduledPack} from './cron.ts';
import {readFileSync} from 'node:fs';

test('daily operations reach their intended pack', () => {
  assert.equal(scheduledPack('0 2 * * *'), 'restaurants');
  assert.equal(scheduledPack('0 1 * * *'), 'backup');
});
test('Sunday follows Cloudflare semantics and case normalization', () => {
  assert.equal(scheduledPack('0 3 * * SUN'), 'population');
  assert.equal(scheduledPack('0 3 * * sun'), 'population');
  assert.equal(scheduledPack('0 3 * * 1'), 'population');
});
test('unsupported triggers cannot silently become backups', () => {
  assert.throws(() => scheduledPack('0 3 * * 0'));
  assert.throws(() => scheduledPack('* * * * *'));
});

test('catalogue and resource checks remain separate deterministic jobs', () => {
  assert.equal(scheduledPack('0 4 * * SUN'), 'catalogue');
  assert.equal(scheduledPack('20 * * * *'), 'resources');
  assert.equal(scheduledPack('2-59/5 * * * *'), 'resources');
});

test('deployed resource cadence matches the capacity model', () => {
  const config=JSON.parse(readFileSync(new URL('./wrangler.jsonc',import.meta.url),'utf8'));
  assert.ok(config.triggers.crons.includes('2-59/5 * * * *'));
  assert.ok(!config.triggers.crons.includes('20 * * * *'));
  const source=readFileSync(new URL('../../src/mcp_open_data_hk/review_config.py',import.meta.url),'utf8');
  assert.equal(Number(source.match(/SCHEDULE_SECONDS = (\d+)/)[1]),300);
});
