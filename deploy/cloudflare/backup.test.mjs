import assert from 'node:assert/strict';
import {test} from 'node:test';
import {saveBackup, MAX_BACKUP, requireCheckpoint, safeOperationError} from './backup.ts';

globalThis.FixedLengthStream = class extends TransformStream {
  constructor(length) {
    let received = 0;
    super({transform(chunk, controller) { received += chunk.length; if (received > length) throw new Error('overflow'); controller.enqueue(chunk); }, flush() { if (received !== length) throw new Error('truncated'); }});
  }
};
function bucket() {
  const objects = new Map([['latest.snapshot.tar.gz', {data:new Uint8Array([9])}]]);
  return {objects, async head(key) {const o=objects.get(key);return o ? {size:o.data.length,customMetadata:o.options?.customMetadata} : null;}, async put(key, body, options) {const data = typeof body === 'string' ? new TextEncoder().encode(body) : new Uint8Array(await new Response(body).arrayBuffer());objects.set(key, {data, options});}, async get(key) {const o=objects.get(key); return o ? {size:o.data.length, body:new Blob([o.data]).stream()} : null;}};
}
function source(bytes, length = bytes.length) {return new Response(new Uint8Array(bytes), {headers:{'content-length':String(length),'x-snapshot-sha256':'a'.repeat(64)}});}
test('checkpoint uses streams and publishes recovery pointers after immutable upload', async () => {
  const BACKUPS=bucket();const receipt=await saveBackup({BACKUPS}, source([1,2,3]), 'test');
  assert.equal(receipt.bytes,3);assert.equal(BACKUPS.objects.size,3);
  assert.deepEqual([...BACKUPS.objects.get('latest.snapshot.tar.gz').data],[1,2,3]);
});
test('truncated checkpoint retains previous recovery pointer', async () => {
  const BACKUPS=bucket();await assert.rejects(saveBackup({BACKUPS}, source([1],2), 'test'));
  assert.deepEqual([...BACKUPS.objects.get('latest.snapshot.tar.gz').data],[9]);
  assert.equal(BACKUPS.objects.has('latest.json'),false);
});
test('invalid or oversized metadata fails before storage', async () => {
  const BACKUPS=bucket();await assert.rejects(saveBackup({BACKUPS}, source([1],MAX_BACKUP+1), 'test'));
  await assert.rejects(saveBackup({BACKUPS}, new Response('x'), 'test'));
  assert.equal(BACKUPS.objects.size,1);
});

test('recovery restart requires the exact accepted checkpoint', async () => {
  const BACKUPS=bucket();await assert.rejects(requireCheckpoint({BACKUPS}, 'a'.repeat(64)));
  await saveBackup({BACKUPS},source([1,2,3]),'test');
  assert.equal((await requireCheckpoint({BACKUPS},'a'.repeat(64))).size,3);
  await assert.rejects(requireCheckpoint({BACKUPS},'b'.repeat(64)));
});

test('private operation errors never expose credentials', () => {
  const token='test-sensitive-value';
  const result=safeOperationError(new Error('Failed '+token+' Bearer another-value'),token);
  assert(!result.includes(token));assert(!result.includes('another-value'));
  assert(result.includes('[redacted]'));
});
