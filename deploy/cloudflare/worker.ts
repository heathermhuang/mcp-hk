import { Container } from '@cloudflare/containers';
import { scheduledPack } from './cron';
import {saveOverview, serveOverview} from './overview';
import {normalizeBackendResponse, recoveringResponse} from './recovery';
import {saveBackup, requireCheckpoint, safeOperationError} from './backup';
import {UsageStore, LIMITS, clientKey, describeRequest, meterResponse} from './usage';


async function authorized(request: Request, token: string): Promise<boolean> {
  if (!token) return false;
  const encoder = new TextEncoder();
  const a = await crypto.subtle.digest('SHA-256', encoder.encode(request.headers.get('authorization') || ''));
  const b = await crypto.subtle.digest('SHA-256', encoder.encode(`Bearer ${token}`));
  return crypto.subtle.timingSafeEqual(a, b);
}

class BodyLimitError extends Error {
  bytesRead: number;
  constructor(bytesRead: number) {super('Body exceeds limit');this.bytesRead=bytesRead;}
}
async function boundedBody(request: Request | Response, limit: number): Promise<Uint8Array> {
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const parts: Uint8Array[] = []; let length = 0;
  for (;;) {
    const {done, value} = await reader.read();
    if (done) break;
    length += value.length;
    if (length > limit) { await reader.cancel(); throw new BodyLimitError(length); }
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

  usageReport(days: number) { return new UsageStore(this.ctx.storage.sql).report(days); }

  async fetch(request: Request): Promise<Response> {
    const started = Date.now(), url = new URL(request.url);
    if (url.pathname.startsWith('/__ops/')) return new Response('Not found', {status: 404});
    const usage = new UsageStore(this.ctx.storage.sql);
    const key = await clientKey(request.headers.get('x-mcp-client-ip') || 'unknown',this.env.OPS_TOKEN);
    const preliminary=usage.quota(key,0,Date.now(),false);
    if (!preliminary.allowed) {
      const response=Response.json({error:{code:'RATE_LIMITED',scope:preliminary.scope}},{status:429,headers:{'Retry-After':String(preliminary.retryAfter),'RateLimit-Limit':String(LIMITS.perMinute),'RateLimit-Remaining':'0','RateLimit-Reset':String(preliminary.retryAfter),'Cache-Control':'no-store','Access-Control-Allow-Origin':'*','Access-Control-Expose-Headers':'RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Retry-After'}});
      const metered=meterResponse(response,describeRequest(request),0,started,(...args)=>usage.record(...args));
      this.ctx.waitUntil(metered.done);return metered.response;
    }
    let body: Uint8Array | undefined;
    if (!['GET','HEAD'].includes(request.method)) {
      try { body = await boundedBody(request, LIMITS.bodyBytes); }
      catch (error) {
        const admission=usage.quota(key,0);
        const response=admission.allowed ? Response.json({error:{code:'BODY_TOO_LARGE'}},{status:413,headers:{'Cache-Control':'no-store','Access-Control-Allow-Origin':'*'}}) : Response.json({error:{code:'RATE_LIMITED',scope:admission.scope}},{status:429,headers:{'Retry-After':String(admission.retryAfter),'Cache-Control':'no-store','Access-Control-Allow-Origin':'*'}});
        const metered=meterResponse(response,describeRequest(request),error instanceof BodyLimitError ? error.bytesRead : 0,started,(...args)=>usage.record(...args));
        this.ctx.waitUntil(metered.done);return metered.response;
      }
    }
    const op = describeRequest(request,body);
    const quota = usage.quota(key,op.sourceCalls);
    const rateHeaders = {'RateLimit-Limit':String(LIMITS.perMinute),'RateLimit-Remaining':String(quota.remaining),'RateLimit-Reset':String(Math.max(1,Math.ceil(quota.reset-Date.now()/1000))),'Cache-Control':'no-store','Access-Control-Allow-Origin':'*','Access-Control-Expose-Headers':'RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Retry-After, MCP-Protocol-Version, Mcp-Session-Id'};
    if (!quota.allowed) {
      const response = Response.json({error:{code:'RATE_LIMITED',message:'Request or source budget exceeded',scope:quota.scope}},{status:429,headers:{...rateHeaders,'Retry-After':String(quota.retryAfter)}});
      const metered = meterResponse(response,op,body?.length || 0,started,(...args)=>usage.record(...args));
      this.ctx.waitUntil(metered.done); return metered.response;
    }
    if (url.pathname === '/mcp' && body) {
      let batch = false;
      try { batch = Array.isArray(JSON.parse(new TextDecoder().decode(body))); } catch { /* Backend handles JSON-RPC parse errors. */ }
      if (batch) {
        const response = Response.json({error:{code:'BATCH_NOT_SUPPORTED',message:'Send one JSON-RPC operation per request'}},{status:400,headers:rateHeaders});
        const metered = meterResponse(response,op,body.length,started,(...args)=>usage.record(...args));
        this.ctx.waitUntil(metered.done); return metered.response;
      }
    }
    const headers = new Headers(request.headers);
    headers.set('x-mcp-edge-token', this.env.OPS_TOKEN);
    const forwarded = new Request(request.url, {method: request.method, headers, body: body ?? request.body, redirect:'manual'});
    let response: Response;
    try { response = await this.containerFetch(forwarded); }
    catch { response = recoveringResponse(this.env.RELEASE_COMMIT); }
    response = await normalizeBackendResponse(response,this.env.RELEASE_COMMIT);
    const result = new Response(response.body,response);
    for (const [name,value] of Object.entries(rateHeaders)) result.headers.set(name,value);
    result.headers.set('Access-Control-Expose-Headers','RateLimit-Limit, RateLimit-Remaining, RateLimit-Reset, Retry-After, MCP-Protocol-Version, Mcp-Session-Id');
    const metered = meterResponse(result,op,body?.length || 0,started,(...args)=>usage.record(...args));
    this.ctx.waitUntil(metered.done); return metered.response;
  }

  async maintain(pack: string) {
    new UsageStore(this.ctx.storage.sql).cleanup();
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
      let overview;
      try { overview = await this.publishOverview(); }
      catch (error) { overview = {status: 'failed', error: safeOperationError(error, this.env.OPS_TOKEN)}; }
      await this.ctx.storage.put('maintenanceStatus', {status: 'success', ...receipt, overview});
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

  async publishOverview() {
    const response = await this.containerFetch(`${this.env.PUBLIC_ORIGIN}/api/v1/coverage`, {headers: {'x-mcp-edge-token': this.env.OPS_TOKEN}, signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error(`Coverage returned ${response.status}`);
    const bytes = await boundedBody(response, 100000);
    return saveOverview(this.env, JSON.parse(new TextDecoder().decode(bytes)));
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
      if (url.pathname === '/__ops/publish-overview' && request.method === 'POST') return Response.json(await env.APP.get(env.APP.idFromName('production')).publishOverview());
      if (url.pathname === '/__ops/restart' && request.method === 'POST') return Response.json(await env.APP.get(env.APP.idFromName('production')).restartFromCheckpoint(request.headers.get('x-snapshot-sha256') || ''));
      if (url.pathname === '/__ops/diagnostics') return Response.json(await env.APP.get(env.APP.idFromName('production')).operationDiagnostics());
      if (url.pathname === '/__ops/usage' && request.method === 'GET') return Response.json(await env.APP.get(env.APP.idFromName('production')).usageReport(Number(url.searchParams.get('days') || 7)),{headers:{'Cache-Control':'no-store'}});
      if (url.pathname === '/__ops/status') return Response.json(await env.APP.get(env.APP.idFromName('production')).operationsStatus());
      return new Response('Not found', {status: 404});
    }
    if (url.pathname === '/api/v1/limits') return Response.json({...LIMITS,window:'UTC fixed minute/day',dailyBudgets:'shared across all clients',mcpBatch:'one JSON-RPC operation per request'},{headers:{'Cache-Control':'public, max-age=300'}});
    if (url.pathname === '/assets/site-config.json') return Response.json({googleAnalyticsId:/^G-[A-Z0-9]{4,20}$/.test(env.GA_MEASUREMENT_ID) ? env.GA_MEASUREMENT_ID : ''},{headers:{'Cache-Control':'no-store'}});
    if (url.pathname === '/assets/overview.json') return serveOverview(env, request);
    if (['/', '/demo', '/sources', '/connect', '/plates', '/coverage', '/data', '/terms', '/privacy'].includes(url.pathname) || url.pathname.startsWith('/assets/')) {
      url.pathname = url.pathname.startsWith('/assets/') ? url.pathname.slice(7) : ['/coverage','/data'].includes(url.pathname) ? '/coverage.html' : ['/terms','/privacy'].includes(url.pathname) ? '/legal.html' : '/index.html';
      const response = await env.ASSETS.fetch(new Request(url, request));
      const secured = new Response(response.body, response);
      secured.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com; img-src 'self' data: https://www.google-analytics.com; frame-ancestors 'none'; base-uri 'none'");
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
