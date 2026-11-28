/** Stream authenticated checkpoints; never buffer expanded inventory in Worker memory. */
export const MAX_BACKUP = 150_000_000;

export const RESOURCE_CHECKPOINT_RETENTION_HOURS = 48;
const rollingPrefix = 'rolling-resource-checkpoints/';
const historicalPrefix = 'backups/';
const generatedKey = /^(?:backups|rolling-resource-checkpoints)\/\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}Z-[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}\.snapshot\.tar\.gz$/;

export async function saveBackup(env: Pick<Env, 'BACKUPS'>, source: Request | Response, reason: string, scheduled = false) {
  const length = Number(source.headers.get('content-length'));
  const sha256 = source.headers.get('x-snapshot-sha256') || '';
  if (!source.body || !Number.isSafeInteger(length) || length < 1 || length > MAX_BACKUP || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid checkpoint length/checksum');
  const createdAt = new Date().toISOString();
  const prefix = scheduled && reason === 'resources' && !source.headers.has('X-Racing-Candidate') ? rollingPrefix : historicalPrefix;
  const key = `${prefix}${createdAt.replaceAll(':', '-')}-${crypto.randomUUID()}.snapshot.tar.gz`;
  const metadata = {sha256, createdAt, reason};
  // FixedLengthStream fails on truncation/overflow. The authenticated producer
  // hashes its SQLite checkpoint; bootstrap independently verifies that checksum.
  const fixed = new FixedLengthStream(length);
  // Container RPC responses can expose TransformStream bodies. Workerd does not
  // implement inter-TransformStream pipeTo(), so pump bounded chunks explicitly.
  const reader = source.body.getReader(), writer = fixed.writable.getWriter();
  const transfer = (async () => {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      await writer.write(value);
    }
    await writer.close();
  })();
  const stored = env.BACKUPS.put(key, fixed.readable, {customMetadata: metadata, httpMetadata: {contentType: 'application/gzip'}});
  try { await Promise.all([transfer, stored]); }
  catch (error) {
    await Promise.allSettled([reader.cancel(error), writer.abort(error)]);
    await Promise.allSettled([transfer, stored]);
    throw error;
  } finally { reader.releaseLock(); writer.releaseLock(); }
  const saved = await env.BACKUPS.get(key);
  if (!saved || saved.size !== length) throw new Error('Incomplete checkpoint upload');
  // Keep the legacy recovery pointer compatible with previously deployed images.
  await env.BACKUPS.put('latest.snapshot.tar.gz', saved.body, {customMetadata: {...metadata, backupKey: key}, httpMetadata: {contentType: 'application/gzip'}});
  const receipt = {key, sha256, createdAt, bytes: length, reason};
  await env.BACKUPS.put('latest.json', JSON.stringify(receipt), {httpMetadata: {contentType: 'application/json'}});
  return receipt;
}

/** Sweep one page per class per maintenance run, advancing only after successful deletes. */
export async function pruneCheckpoints(bucket: R2Bucket, storage: DurableObjectStorage, now = Date.now()) {
  const [root, manifest] = await Promise.all([bucket.head('latest.snapshot.tar.gz'), bucket.get('latest.json')]);
  if (!manifest || manifest.size > 4096) throw new Error('Checkpoint manifest unavailable');
  const receipt = await manifest.json<{key?: unknown}>();
  const rootKey = root?.customMetadata?.backupKey;
  const manifestKey = receipt?.key;
  if (!rootKey || !generatedKey.test(rootKey) || typeof manifestKey !== 'string' || !generatedKey.test(manifestKey)) {
    throw new Error('Invalid checkpoint retention pointers');
  }
  for (const [prefix, hours] of [[rollingPrefix, RESOURCE_CHECKPOINT_RETENTION_HOURS], [historicalPrefix, 30 * 24]] as const) {
    const cursorKey = 'checkpointPruneCursor:' + prefix;
    const cursor = await storage.get<string>(cursorKey);
    const page = await bucket.list({prefix, cursor, limit: 128});
    const expired = page.objects.filter(object =>
      object.key.startsWith(prefix) && generatedKey.test(object.key) &&
      object.key !== rootKey && object.key !== manifestKey && object.uploaded.getTime() < now - hours * 3600000
    ).map(object => object.key);
    if (expired.length) await bucket.delete(expired);
    if (page.truncated) await storage.put(cursorKey, page.cursor);
    else if (cursor) await storage.delete(cursorKey);
  }
}

/** Recovery must name the exact accepted checkpoint before stopping an instance. */
export async function requireCheckpoint(env: Pick<Env, 'BACKUPS'>, sha256: string) {
  if (!/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Expected checkpoint checksum required');
  const object = await env.BACKUPS.head('latest.snapshot.tar.gz');
  if (!object || object.customMetadata?.sha256 !== sha256 || object.size < 1 || object.size > MAX_BACKUP) throw new Error('Accepted checkpoint changed or is missing');
  return object;
}


export function safeOperationError(error: unknown, token: string): string {
  let message = error instanceof Error ? error.message : 'Unknown checkpoint error';
  if (token) message = message.replaceAll(token, '[redacted]');
  return message.replace(/Bearer\s+\S+/gi, 'Bearer [redacted]').slice(0, 500);
}
