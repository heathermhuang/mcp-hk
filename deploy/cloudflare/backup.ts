/** Stream authenticated checkpoints; never buffer expanded inventory in Worker memory. */
export const MAX_BACKUP = 150_000_000;

export async function saveBackup(env: Pick<Env, 'BACKUPS'>, source: Request | Response, reason: string) {
  const length = Number(source.headers.get('content-length'));
  const sha256 = source.headers.get('x-snapshot-sha256') || '';
  if (!source.body || !Number.isSafeInteger(length) || length < 1 || length > MAX_BACKUP || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid checkpoint length/checksum');
  const createdAt = new Date().toISOString();
  const key = `backups/${createdAt.replaceAll(':', '-')}-${crypto.randomUUID()}.snapshot.tar.gz`;
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
