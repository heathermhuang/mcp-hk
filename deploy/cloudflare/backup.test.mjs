import assert from 'node:assert/strict';
import {test} from 'node:test';
import {saveBackup, MAX_BACKUP, requireCheckpoint, safeOperationError, pruneCheckpoints} from './backup.ts';

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

test('container transform bodies do not require unsupported inter-stream pipeTo', async () => {
  const BACKUPS=bucket();const response=source([1,2,3]);
  Object.defineProperty(response.body,'pipeTo',{value:() => {throw new TypeError('Inter-TransformStream ReadableStream.pipeTo() is not implemented.');}});
  const receipt=await saveBackup({BACKUPS},response,'container-backup');
  assert.equal(receipt.bytes,3);
  assert.deepEqual([...BACKUPS.objects.get('latest.snapshot.tar.gz').data],[1,2,3]);
});

test('only scheduled resources without a racing candidate receive short retention', async () => {
  for (const [reason, scheduled, candidate, rolling] of [
    ['resources',true,null,true], ['resources',false,null,false], ['resources-recovery',false,null,false],
    ['resources',true,'racing-results-v1-'+'a'.repeat(64),false], ['resources',true,'',false],
    ['resources',true,'invalid',false], ['backup',true,null,false], ['catalogue',true,null,false],
    ['racing-accepted',false,null,false], ['operator-seed',false,null,false],
  ]) {
    const response=source([1,2,3]);
    if (candidate !== null) response.headers.set('X-Racing-Candidate',candidate);
    const receipt=await saveBackup({BACKUPS:bucket()},response,reason,scheduled);
    assert.equal(receipt.key.split('/')[0], rolling ? 'rolling-resource-checkpoints' : 'backups');
  }
});

test('failed publication preserves recoverable bytes and exposes both immutable references', async () => {
  const BACKUPS=bucket();
  const first=await saveBackup({BACKUPS},source([1]),'backup');
  await assert.rejects(saveBackup({BACKUPS},source([2],2),'resources',true));
  assert.equal((await BACKUPS.head('latest.snapshot.tar.gz')).customMetadata.backupKey,first.key);
  const put=BACKUPS.put.bind(BACKUPS);
  BACKUPS.put=(key,...args)=>{if(key==='latest.json')throw new Error('manifest unavailable');return put(key,...args);};
  await assert.rejects(saveBackup({BACKUPS},source([2]),'resources',true));
  const rootKey=(await BACKUPS.head('latest.snapshot.tar.gz')).customMetadata.backupKey;
  assert.notEqual(rootKey,first.key);
  assert.deepEqual([...BACKUPS.objects.get(rootKey).data],[2]);
  assert.equal(JSON.parse(new TextDecoder().decode(BACKUPS.objects.get('latest.json').data)).key,first.key);
});

function retentionFixture() {
  const now=Date.UTC(2026,10,28);
  const objects=new Map(), cursors=new Map(), requests=[];
  const rolling='rolling-resource-checkpoints/', history='backups/';
  function add(prefix,hours,id) {
    const uploaded=new Date(now-hours*3600000);
    const stamp=uploaded.toISOString().replaceAll(':','-');
    const key=prefix+stamp+'-00000000-0000-4000-8000-'+String(id).padStart(12,'0')+'.snapshot.tar.gz';
    objects.set(key,{key,uploaded});
    return key;
  }
  const root=add(rolling,80,1), manifest=add(history,31*24,2);
  const bucket={
    async head(){return {customMetadata:{backupKey:root}};},
    async get(){return {size:100,json:async()=>({key:manifest})};},
    async list({prefix,cursor='',limit}){
      requests.push({prefix,cursor,limit});
      const keys=[...objects.keys()].filter(k=>k.startsWith(prefix)&&k>cursor).sort();
      const page=keys.slice(0,limit);
      return {objects:page.map(k=>objects.get(k)),truncated:keys.length>limit,cursor:page.at(-1)};
    },
    async delete(keys){for(const k of keys)objects.delete(k);},
  };
  const storage={get:k=>cursors.get(k),put:(k,v)=>cursors.set(k,v),delete:k=>cursors.delete(k)};
  return {now,objects,cursors,requests,rolling,history,root,manifest,add,bucket,storage};
}

test('age, current pointers, key shape and prefix constrain bounded retention pages',async()=>{
  const f=retentionFixture();
  const expired=Array.from({length:260},(_,i)=>f.add(f.rolling,50,i));
  const protectedKeys=[f.root,f.manifest,f.add(f.rolling,48,3),f.add(f.history,30*24,4),f.add('company/',1000,6)];
  const invalid=f.rolling+'unrelated';
  f.objects.set(invalid,{key:invalid,uploaded:new Date(0)});
  const oldHistory=f.add(f.history,31*24,5);
  await pruneCheckpoints(f.bucket,f.storage,f.now);
  assert.equal(f.requests.length,2);
  assert.ok(f.objects.has(expired.at(-1)));
  assert.ok(!f.objects.has(oldHistory));
  await pruneCheckpoints(f.bucket,f.storage,f.now);
  await pruneCheckpoints(f.bucket,f.storage,f.now);
  assert.ok(f.requests[2].cursor);
  assert.equal(f.cursors.size,0);
  for(const key of expired)assert.ok(!f.objects.has(key));
  for(const key of [...protectedKeys,invalid])assert.ok(f.objects.has(key));
});

test('cleanup fails closed for absent, malformed or unreadable pointers',async()=>{
  for(const changes of [
    {head:async()=>null},{get:async()=>null},{head:async()=>({customMetadata:{backupKey:'other/key'}})},
    {get:async()=>({size:5,json:async()=>({key:'other/key'})})},{get:async()=>{throw new Error('R2 unavailable');}},
  ]){
    const f=retentionFixture();
    await assert.rejects(pruneCheckpoints({...f.bucket,...changes},f.storage,f.now));
    assert.equal(f.requests.length,0);
  }
});

test('failed page deletion leaves the page available for retry',async()=>{
  const f=retentionFixture();
  const expired=Array.from({length:140},(_,i)=>f.add(f.rolling,50,i));
  await assert.rejects(pruneCheckpoints({...f.bucket,delete:async()=>{throw new Error('delete unavailable');}},f.storage,f.now));
  assert.equal(f.cursors.size,0);
  await pruneCheckpoints(f.bucket,f.storage,f.now);
  await pruneCheckpoints(f.bucket,f.storage,f.now);
  assert.ok(expired.every(key=>!f.objects.has(key)));
});
