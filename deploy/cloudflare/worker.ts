import { Container } from '@cloudflare/containers';
import { scheduledPack } from './cron';
import {normalizeBackendResponse, recoveringResponse} from './recovery';
import {saveBackup, requireCheckpoint, safeOperationError} from './backup';


async function authorized(request: Request, token: string): Promise<boolean> {
  if (!token) return false;
  const encoder = new TextEncoder();
  const a = await crypto.subtle.digest('SHA-256', encoder.encode(request.headers.get('authorization') || ''));
  const b = await crypto.subtle.digest('SHA-256', encoder.encode(`Bearer ${token}`));
  return crypto.subtle.timingSafeEqual(a, b);
}

async function boundedBody(request: Request | Response, limit: number): Promise<Uint8Array> {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const parts: Uint8Array[] = []; let length = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    length += value.length;
    if (length > limit) { await reader.cancel(); throw new Error('Body exceeds limit'); }
    parts.push(value);
  }
  const result = new Uint8Array(length); let offset = 0;
  for (const p of parts) { result.set(p, offset); offset += p.length; }
  return result;
}

export class McpContainer extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = '2m';
  envVars = {
    MCP_HK_DATABASE: '/data/mcp-hk.sqlite3', HOST: '0.0.0.0', PORT: '8000',
    MCP_HK_OPS_TOKEN: this.env.OPS_TOKEN,
    MCP_HK_BOOTSTRAP_URL: `${this.env.BOOTSTRAP_ORIGIN}/__ops/snapshot`,
    MCP_HK_EDGE_MODE: 'true',
    MCP_HK_ALLOWED_HOSTS: 'mcp.hk,mcp-hk.measurable.workers.dev,localhost,127.0.0.1,container',
    MCP_HK_ALLOWED_ORIGINS: 'https://mcp.hk,https://mcp-hk.measurable.workers.dev,http://localhost:8000',
  };
  entrypoint = ['mcp-hk-container'];

  private quota(ip: string, sourceCalls: number) {
    const now = Date.now(), minute = Math.floor(now / 60000), day = Math.floor(now / 86400000);
    const sql = this.ctx.storage.sql;
    sql.exec('CREATE TABLE IF NOT EXISTS rate (ip TEXT, minute INTEGER, count INTEGER, PRIMARY KEY(ip,minute))');
    sql.exec('CREATE TABLE IF NOT EXISTS daily (day INTEGER PRIMARY KEY, calls INTEGER, addresses INTEGER)');
    sql.exec('DELETE FROM rate WHERE minute < ?', minute - 2);
    sql.exec('DELETE FROM daily WHERE day < ?', day - 2);
    const rate = [...sql.exec<{count: number}>('SELECT count FROM rate WHERE ip=? AND minute=?', ip, minute)][0]?.count || 0;
    const daily = [...sql.exec<{calls: number; addresses: number}>('SELECT calls,addresses FROM daily WHERE day=?', day)][0] || {calls: 0, addresses: 0};
    if (rate >= 60 || daily.calls >= 50000 || (sourceCalls && daily.addresses + sourceCalls > 10000)) return false;
    sql.exec('INSERT INTO rate VALUES (?,?,1) ON CONFLICT(ip,minute) DO UPDATE SET count=count+1', ip, minute);
    sql.exec('INSERT INTO daily VALUES (?,1,?) ON CONFLICT(day) DO UPDATE SET calls=calls+1,addresses=addresses+excluded.addresses', day, sourceCalls);
    return true;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/__ops/')) return new Response('Not found', {status: 404});
    let body: Uint8Array | undefined, sourceCalls = url.pathname.startsWith('/api/v1/addresses') ? 1 : 0;
    if (request.method === 'POST') {
      try { body = await boundedBody(request, 65536); } catch { return Response.json({error: {code: 'BODY_TOO_LARGE'}}, {status: 413}); }
      if (url.pathname === '/mcp') {
        try {
          const parsed = JSON.parse(new TextDecoder().decode(body));
          const calls = Array.isArray(parsed) ? parsed : [parsed];
          sourceCalls = calls.filter(call => call.method === 'tools/call' && ['hk_address_search', 'hk_address_get'].includes(call.params?.name)).length;
        } catch { /* The MCP transport returns its own JSON-RPC parse error. */ }
      }
    }
    const ip = request.headers.get('x-mcp-client-ip') || 'unknown';
    if (!this.quota(ip, sourceCalls)) return Response.json({error: {code: 'RATE_LIMITED', message: 'Request or source budget exceeded'}}, {status: 429, headers: {'Retry-After': '60'}});
    const headers = new Headers(request.headers);
    headers.set('x-mcp-edge-token', this.env.OPS_TOKEN);
    const forwarded = new Request(request.url, {method: request.method, headers, body: body ?? request.body, redirect: 'manual'});
    return this.containerFetch(forwarded);
  }

  async maintain(pack: string) {
    const now = Date.now();
    const lease = await this.ctx.storage.get<number>('maintenanceLease');
    if (lease && lease > now) throw new Error('Maintenance already running');
    // No await between checking and writing the lease's transaction boundary.
    const acquired = await this.ctx.storage.transaction(async txn => {
      if ((await txn.get<number>('maintenanceLease') || 0) > Date.now()) return false;
      await txn.delete('seedOwner');
      await txn.put('maintenanceLease', Date.now() + 15 * 60000); return true;
    });
    if (!acquired) throw new Error('Maintenance already running');
    try {
      const path = pack === 'backup' ? '/__ops/backup' : `/__ops/refresh?pack=${pack}`;
      const response = await this.containerFetch(`${this.env.PUBLIC_ORIGIN}${path}`, {method: 'POST', headers: {'Authorization': `Bearer ${this.env.OPS_TOKEN}`, 'x-mcp-edge-token': this.env.OPS_TOKEN}});
      if (!response.ok) throw new Error(`Maintenance source returned ${response.status}`);
      const receipt = await saveBackup(this.env, response, pack);
      await this.ctx.storage.put('maintenanceStatus', {status: 'success', ...receipt});
      const cutoff = Date.now() - 30 * 86400000;
      const versions = await this.env.BACKUPS.list({prefix: 'backups/'});
      const expired = versions.objects.filter(object => object.uploaded.getTime() < cutoff).map(object => object.key);
      if (expired.length) await this.env.BACKUPS.delete(expired);
      return receipt;
    } catch (error) {
      await this.ctx.storage.put('maintenanceStatus', {status: 'failed', attemptedAt: new Date().toISOString(), pack, error: safeOperationError(error, this.env.OPS_TOKEN)});
      throw new Error('Maintenance failed; previous backup retained');
    } finally { await this.ctx.storage.delete('maintenanceLease'); }
  }

  async claimSeedLease() {
    const owner = crypto.randomUUID();
    const acquired = await this.ctx.storage.transaction(async txn => {
      if ((await txn.get<number>('maintenanceLease') || 0) > Date.now()) return false;
      await txn.put('maintenanceLease', Date.now() + 15 * 60000);
      await txn.put('seedOwner', owner); return true;
    });
    if (!acquired) throw new Error('Maintenance already running');
    return owner;
  }

  async releaseSeedLease(owner: string) {
    await this.ctx.storage.transaction(async txn => {
      if (await txn.get<string>('seedOwner') !== owner) return;
      await txn.delete('seedOwner'); await txn.delete('maintenanceLease');
    });
  }

  async restartFromCheckpoint(sha256: string) {
    const acquired = await this.ctx.storage.transaction(async txn => {
      if ((await txn.get<number>('maintenanceLease') || 0) > Date.now()) return false;
      await txn.delete('seedOwner');
      await txn.put('maintenanceLease', Date.now() + 15 * 60000); return true;
    });
    if (!acquired) throw new Error('Maintenance already running');
    try {
      await requireCheckpoint(this.env, sha256);
      await this.stop();
      return {status: 'stopped', checkpointSha256: sha256, recovery: 'Next request restores the accepted R2 checkpoint'};
    } finally { await this.ctx.storage.delete('maintenanceLease'); }
  }

  async operationDiagnostics() {
    return {leaseUntil: await this.ctx.storage.get<number>('maintenanceLease') || null,
      seedLease: Boolean(await this.ctx.storage.get<string>('seedOwner')),
      now: Date.now(), maintenance: await this.operationsStatus()};
  }

  async operationsStatus() { return await this.ctx.storage.get('maintenanceStatus') || {status: 'not_run'}; }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(url.hostname)) return Response.redirect(`https://${url.host}${url.pathname}${url.search}`, 308);
    if (url.hostname === 'www.mcp.hk') return Response.redirect(`https://mcp.hk${url.pathname}${url.search}`, 308);
    if (url.pathname.startsWith('/__ops/')) {
      if (!(await authorized(request, env.OPS_TOKEN))) return new Response('Not found', {status: 404});
      if (url.pathname === '/__ops/snapshot' && request.method === 'GET') {
        const object = await env.BACKUPS.get('latest.snapshot.tar.gz');
        if (!object) return new Response('No accepted snapshot', {status: 503});
        return new Response(object.body, {headers: {'Content-Type': 'application/gzip', 'X-Snapshot-SHA256': object.customMetadata?.sha256 || '', 'Cache-Control': 'no-store'}});
      }
      if (url.pathname === '/__ops/snapshot' && request.method === 'POST') {
        const app = env.APP.get(env.APP.idFromName('production'));
        let owner: string | undefined, receipt: unknown, failure: {phase: string; message: string} | undefined;
        let phase = 'lease';
        try {
          owner = await app.claimSeedLease(); phase = 'upload';
          receipt = await saveBackup(env, request, 'operator-seed');
        } catch (error) { failure = {phase, message: safeOperationError(error, env.OPS_TOKEN)}; }
        if (owner) {
          try { await app.releaseSeedLease(owner); }
          catch (error) { failure ||= {phase: 'release', message: safeOperationError(error, env.OPS_TOKEN)}; }
        }
        return failure ? Response.json({error: {code: 'CHECKPOINT_OPERATION_FAILED', ...failure}}, {status: failure.phase === 'lease' ? 409 : 500}) : Response.json(receipt);
      }
      if (url.pathname === '/__ops/run' && request.method === 'POST') {
        const pack = url.searchParams.get('pack') || 'backup';
        if (!['backup', 'restaurants', 'population', 'all', 'catalogue', 'resources'].includes(pack)) return new Response('Invalid pack', {status: 400});
        return Response.json(await env.APP.get(env.APP.idFromName('production')).maintain(pack));
      }
      if (url.pathname === '/__ops/restart' && request.method === 'POST') return Response.json(await env.APP.get(env.APP.idFromName('production')).restartFromCheckpoint(request.headers.get('x-snapshot-sha256') || ''));
      if (url.pathname === '/__ops/diagnostics') return Response.json(await env.APP.get(env.APP.idFromName('production')).operationDiagnostics());
      if (url.pathname === '/__ops/status') return Response.json(await env.APP.get(env.APP.idFromName('production')).operationsStatus());
      return new Response('Not found', {status: 404});
    }
    if (['/', '/demo', '/sources', '/connect', '/plates', '/coverage', '/data'].includes(url.pathname) || url.pathname.startsWith('/assets/')) {
      url.pathname = url.pathname.startsWith('/assets/') ? url.pathname.slice(7) : ['/coverage','/data'].includes(url.pathname) ? '/coverage.html' : '/index.html';
      const response = await env.ASSETS.fetch(new Request(url, request));
      const secured = new Response(response.body, response);
      secured.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'");
      secured.headers.set('X-Content-Type-Options', 'nosniff');
      secured.headers.set('Referrer-Policy', 'no-referrer');
      secured.headers.set('X-Mcp-Release', env.RELEASE_COMMIT);
      secured.headers.set('Strict-Transport-Security', 'max-age=31536000');
      return secured;
    }
    if (url.pathname === '/api/v1/operations') {
      const manifest = await env.BACKUPS.get('latest.json');
      return Response.json({backup: manifest ? await manifest.json() : null, maintenance: await env.APP.get(env.APP.idFromName('production')).operationsStatus(), schedules: {catalogue: 'Sunday 12:00 Asia/Hong_Kong', resources: 'every hour at minute 20, 20 resources per batch', restaurants: 'daily 10:00 Asia/Hong_Kong', population: 'Sunday 11:00 Asia/Hong_Kong', backup: 'daily 09:00 Asia/Hong_Kong'}, retentionDays: 30});
    }
    const headers = new Headers(request.headers);
    headers.set('x-mcp-client-ip', request.headers.get('cf-connecting-ip') || 'unknown');
    try {
      const response = await env.APP.get(env.APP.idFromName('production')).fetch(new Request(request, {headers}));
      return normalizeBackendResponse(response, env.RELEASE_COMMIT);
    } catch {
      return recoveringResponse(env.RELEASE_COMMIT);
    }
  },
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    const pack = scheduledPack(controller.cron);
    ctx.waitUntil(env.APP.get(env.APP.idFromName('production')).maintain(pack));
  },
} satisfies ExportedHandler<Env>;
