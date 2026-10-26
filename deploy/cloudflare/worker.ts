import {hkexDailyBackup,hkexDailyBackupAdmission} from './hkex-daily-backup';
import {officialBackup,officialBackupAdmission} from './official-backup';
import {companyDownloads,publishCompanyDownload} from './company-downloads';
import { Container } from '@cloudflare/containers';
import { DurableObject } from 'cloudflare:workers';
import {AgentAuthService,isAgentAuthPath,protectedDataPath,dataRequestHeaders} from './agent-auth';
import {discoveryTarget,discoveryLinks} from './discovery';
import { scheduledPack } from './cron';
import {maintenanceResponse, maintenanceRuntimeReady, scheduledMaintenance, maintenancePackForRequest, EXPECTED_REVIEW_POLICY, enqueueScheduled, nextScheduled, settleScheduled, scheduledStatus} from './maintenance';
import {probePublicSource} from './source-probe';
import {relayApprovedSource} from './source-relay';
import {saveOverview, serveOverview} from './overview';
import {normalizeBackendResponse, recoveringResponse} from './recovery';
import {saveBackup, requireCheckpoint, safeOperationError} from './backup';
import {completeRacingPublication} from './racing-publication';
import {RacingAdmission} from './racing-admission';
import {curatedContainerEnv} from './curated';
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

export class AgentAuth extends DurableObject<Env> {
  private service: AgentAuthService;
  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx,env);
    this.service=new AgentAuthService(ctx.storage.sql,env.PUBLIC_ORIGIN);
    ctx.blockConcurrencyWhile(()=>this.service.init());
  }
  async fetch(request: Request): Promise<Response> {
    if(!await this.ctx.storage.getAlarm())await this.ctx.storage.setAlarm(Date.now()+3600000);
    return this.service.handle(request);
  }
  async alarm(): Promise<void> {
    this.service.cleanup();
    if(this.service.hasExpiringRecords())await this.ctx.storage.setAlarm(Date.now()+3600000);
  }
  async revokeAll(): Promise<void> {this.service.revokeAll();}
}

export class McpContainer extends Container<Env> {
  racingAdmission(input:{action:string;id?:string;referenceId?:string;state?:string;bytes?:number;code?:string|null}){
    const admission=new RacingAdmission(this.ctx.storage.sql);
    if(input.action==='reserve')return admission.reserve(String(input.id));
    if(input.action==='inspect_redirect')return admission.reserveRedirectInspection(String(input.referenceId),String(input.id));
    if(input.action==='inspect_redirect_shape')return admission.reserveRedirectInspection(String(input.referenceId),String(input.id),Date.now(),true);
    if(input.action==='settle')return admission.settle(String(input.id),String(input.state),Number(input.bytes),input.code??null);
    if(input.action==='status')return admission.report();
    throw new Error('RACING_ADMISSION_ACTION');
  }
  private downloads = companyDownloads(this.env.BACKUPS);
  defaultPort = 8000;
  // Keep the runtime warm across the five-minute review cadence.
  sleepAfter = '10m';
  envVars = {
    ...curatedContainerEnv(this.env,this.env.CURATED_BACKEND_ORIGIN),
    MCP_HK_DATABASE: '/data/mcp-hk.sqlite3', HOST: '0.0.0.0', PORT: '8000',
    MCP_HK_OPS_TOKEN: this.env.OPS_TOKEN,
    MCP_HK_BOOTSTRAP_URL: `${this.env.BOOTSTRAP_ORIGIN}/__ops/snapshot`,
    MCP_HK_EDGE_MODE: 'true',
    MCP_HK_ALLOWED_HOSTS: 'mcp.hk,mcp-hk.measurable.workers.dev,localhost,127.0.0.1,container',
    MCP_HK_ALLOWED_ORIGINS: 'https://mcp.hk,https://mcp-hk.measurable.workers.dev,http://localhost:8000',
  };
  entrypoint = ['mcp-hk-container'];

  hkexDailyBackupAdmission(bytes:number,write:boolean):boolean {return hkexDailyBackupAdmission(this.ctx.storage.sql,bytes,write);}

  officialBackupAdmission(bytes:number,write:boolean):boolean {return officialBackupAdmission(this.ctx.storage.sql,bytes,write);}

  usageReport(days: number) { return new UsageStore(this.ctx.storage.sql).report(days); }

  async publishCompanyExport(input: unknown) {
    const owner = await this.claimSeedLease();
    try {return await publishCompanyDownload(this.env.BACKUPS,input);}
    finally {await this.releaseSeedLease(owner);}
  }

  private async acceptRacingCandidate(response: Response, receipt: Awaited<ReturnType<typeof saveBackup>>) {
    return completeRacingPublication(response,receipt,
      (version,digest)=>this.containerFetch(`${this.env.PUBLIC_ORIGIN}/__ops/racing/qualify`,{method:'POST',headers:{'Authorization':`Bearer ${this.env.OPS_TOKEN}`,'x-mcp-edge-token':this.env.OPS_TOKEN,'Content-Type':'application/json'},body:JSON.stringify({version,backupSha256:digest})}),
      accepted=>saveBackup(this.env,accepted,'racing-accepted'));
  }

  async racingOperation(body: Uint8Array) {
    const health=await this.containerFetch(`${this.env.PUBLIC_ORIGIN}/healthz`,{headers:{'x-mcp-edge-token':this.env.OPS_TOKEN},signal:AbortSignal.timeout(15000)});
    if(!health.ok||JSON.parse(new TextDecoder().decode(await boundedBody(health,2000))).racingPipeline!=='results-r2-v1')throw new Error('RACING_PIPELINE_RUNTIME_NOT_READY');
    const owner=await this.claimSeedLease();
    try {
      const input=JSON.parse(new TextDecoder().decode(body));
      if(input.action==='profile_import')new RacingAdmission(this.ctx.storage.sql).verifyProfileImport(input.captures,input.admissions);
      if(input.action==='import'){
        const attempts=input.bundle?.attempts;if(!Array.isArray(attempts)||attempts.length>200)throw new Error('RACING_IMPORT_ATTEMPTS');
        const events=[];
        for(const attempt of attempts){
          if(typeof attempt.url!=='string'||!attempt.url.startsWith('https://racing.hkjc.com/')||!['success','reviewed_parser','reviewed_layout','reviewed_input'].includes(attempt.state))throw new Error('RACING_IMPORT_RECEIPT');
          const raw=new TextEncoder().encode(attempt.url+'\0'+attempt.at),hash=await crypto.subtle.digest('SHA-256',raw);
          events.push({id:'import-'+Array.from(new Uint8Array(hash),b=>b.toString(16).padStart(2,'0')).join(''),at:Number(attempt.at)*1000,bytes:Number(attempt.bytes)});
        }
        new RacingAdmission(this.ctx.storage.sql).seed(events);
      }
      const response=await this.containerFetch(`${this.env.PUBLIC_ORIGIN}/__ops/racing`,{method:'POST',headers:{'Authorization':`Bearer ${this.env.OPS_TOKEN}`,'x-mcp-edge-token':this.env.OPS_TOKEN,'Content-Type':'application/json'},body});
      if(!response.ok){await response.body?.cancel();throw new Error('RACING_OPERATION_REJECTED');}
      const inspection=response.headers.get('X-Racing-Inspection');
      if(inspection&&inspection.length>4096){await response.body?.cancel();throw new Error('RACING_INSPECTION_RECEIPT_BOUND');}
      let inspectionReceipt;
      try {
        inspectionReceipt=inspection===null?undefined:JSON.parse(inspection);
        if(inspection!==null&&(!inspectionReceipt||typeof inspectionReceipt!=='object'||Array.isArray(inspectionReceipt)||!['inspect_redirect','inspect_redirect_shape'].includes(input.action)||inspectionReceipt.originalAttempt!==input.attempt||inspectionReceipt.originalHoldRetained!==true))throw new Error('invalid');
      } catch {await response.body?.cancel();throw new Error('RACING_INSPECTION_RECEIPT_INVALID');}
      const receipt=await saveBackup(this.env,response,'racing-operator');
      return {...await this.acceptRacingCandidate(response,receipt),...(inspectionReceipt?{inspection:inspectionReceipt}:{})};
    } finally {await this.releaseSeedLease(owner);}
  }

  async runScheduled(pack: string, scheduledAt: number) {
    await enqueueScheduled(this.ctx.storage, pack, scheduledAt);
    return scheduledMaintenance(this, 'scheduled');
  }

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
    // Repeat the boundary at the data-controller hop, retaining only the identity
    // already replaced by the trusted edge Worker for quota accounting.
    const headers = dataRequestHeaders(request,request.headers.get('x-mcp-client-ip')||'unknown');
    headers.set('x-mcp-edge-token', this.env.OPS_TOKEN);
    headers.set('x-mcp-racing-budget',JSON.stringify(new RacingAdmission(this.ctx.storage.sql).report()));
    const forwarded = new Request(request.url, {method: request.method, headers, body: body ?? request.body, redirect:'manual'});
    let response: Response;
    try { response = await this.downloads(forwarded) || await this.containerFetch(forwarded); }
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
    new RacingAdmission(this.ctx.storage.sql).cleanup();
    const now = Date.now();
    const lease = await this.ctx.storage.get<number>('maintenanceLease');
    if (lease && lease > now) throw new Error('Maintenance already running');
    // A rollout can serve the new Worker before the data image is ready. Never
    // claim a long safety lease for a job that cannot run on that image yet.
    try {
      const response = await this.containerFetch(`${this.env.PUBLIC_ORIGIN}/healthz`, {headers:{'x-mcp-edge-token':this.env.OPS_TOKEN},signal:AbortSignal.timeout(15000)});
      const bytes = await boundedBody(response, 2000);
      if (!response.ok || !maintenanceRuntimeReady(JSON.parse(new TextDecoder().decode(bytes)))) throw new Error('DATA_RUNTIME_NOT_READY');
    } catch { throw new Error('DATA_RUNTIME_NOT_READY'); }
    // No await between checking and writing the lease's transaction boundary.
    const acquired = await this.ctx.storage.transaction(async txn => {
      if ((await txn.get<number>('maintenanceLease') || 0) > Date.now()) return false;
      await txn.delete('seedOwner');
      await txn.put('maintenanceLease', Date.now() + 15 * 60000); return true;
    });
    if (!acquired) throw new Error('Maintenance already running');
    let scheduled;
    try {
      if (pack === 'scheduled') {
        scheduled = await nextScheduled(this.ctx.storage);
        pack = scheduled?.pack || 'resources';
      }
      const path = pack === 'backup' ? '/__ops/backup' : `/__ops/refresh?pack=${pack}`;
      const response = await this.containerFetch(`${this.env.PUBLIC_ORIGIN}${path}`, {method: 'POST', headers: {'Authorization': `Bearer ${this.env.OPS_TOKEN}`, 'x-mcp-edge-token': this.env.OPS_TOKEN}});
      if (!response.ok) throw new Error(`Maintenance source returned ${response.status}`);
      const saved = await saveBackup(this.env, response, pack);
      const receipt = await this.acceptRacingCandidate(response,saved);
      let overview;
      try { overview = await this.publishOverview(); }
      catch (error) { overview = {status: 'failed', error: safeOperationError(error, this.env.OPS_TOKEN)}; }
      await this.ctx.storage.put('maintenanceStatus', {status: 'success', ...receipt, overview});
      if (scheduled) await settleScheduled(this.ctx.storage, scheduled, 'success');
      const cutoff = Date.now() - 30 * 86400000;
      const versions = await this.env.BACKUPS.list({prefix: 'backups/'});
      const expired = versions.objects.filter(object => object.uploaded.getTime() < cutoff).map(object => object.key);
      if (expired.length) await this.env.BACKUPS.delete(expired);
      return receipt;
    } catch (error) {
      if (scheduled) await settleScheduled(this.ctx.storage, scheduled, 'failed');
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
    return {workerRelease: this.env.RELEASE_COMMIT || null, controllerContract:'source-aware-ux-1', credentialBoundary:'edge-and-controller-v1', maintenancePolicy: EXPECTED_REVIEW_POLICY, idleTimeout: this.sleepAfter, leaseUntil: await this.ctx.storage.get<number>('maintenanceLease') || null,
      seedLease: Boolean(await this.ctx.storage.get<string>('seedOwner')),
      now: Date.now(), maintenance: await this.operationsStatus(), scheduled: await scheduledStatus(this.ctx.storage)};
  }

  async operationsStatus() { return await this.ctx.storage.get('maintenanceStatus') || {status: 'not_run'}; }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if(isAgentAuthPath(url.pathname)&&url.origin!==env.PUBLIC_ORIGIN)return new Response('Use the canonical mcp.hk origin',{status:400,headers:{'Cache-Control':'no-store'}});
    if (url.protocol !== 'https:' && !['localhost', '127.0.0.1'].includes(url.hostname)) return Response.redirect(`https://${url.host}${url.pathname}${url.search}`, 308);
    if (url.hostname === 'www.mcp.hk') return Response.redirect(`https://mcp.hk${url.pathname}${url.search}`, 308);
    if(url.pathname.startsWith('/__hkex-daily-backup/'))return hkexDailyBackup(request,env,(bytes,write)=>env.APP.get(env.APP.idFromName('production')).hkexDailyBackupAdmission(bytes,write));
    if(url.pathname.startsWith('/__company-backup/'))return officialBackup(request,env,(bytes,write)=>env.APP.get(env.APP.idFromName('production')).officialBackupAdmission(bytes,write));
    if (isAgentAuthPath(url.pathname)) {
      // Credentials/cookies belong only to the canonical host. Never redirect POST secrets.
      const headers=new Headers(request.headers);
      headers.set('x-auth-client-key',await clientKey(request.headers.get('cf-connecting-ip')||'unknown',env.OPS_TOKEN));
      const response=await env.AGENT_AUTH.get(env.AGENT_AUTH.idFromName('production')).fetch(new Request(request,{headers}));
      const target=protectedDataPath(url.pathname);
      if(!target||!response.ok){const result=new Response(response.body,response);result.headers.set('X-Mcp-Release',env.RELEASE_COMMIT);return result;}
      // Auth is checked durably on every request. Keep existing IP/shared data budgets.
      await response.body?.cancel();url.pathname=target;
      const result=await env.APP.get(env.APP.idFromName('production')).fetch(new Request(url,{method:request.method,headers:dataRequestHeaders(request),redirect:'manual'}));
      return normalizeBackendResponse(result,env.RELEASE_COMMIT);
    }
    if (url.pathname.startsWith('/__ops/')) {
      if (!(await authorized(request, env.OPS_TOKEN))) return new Response('Not found', {status: 404});
      if(url.pathname==='/__ops/racing'&&request.method==='POST') {
        try {
          const body=await boundedBody(request,16*1024*1024);
          return Response.json(await env.APP.get(env.APP.idFromName('production')).racingOperation(body),{headers:{'Cache-Control':'no-store'}});
        } catch {return Response.json({error:{code:'RACING_OPERATION_NOT_CONFIRMED',message:'Inspect the preserved source/candidate receipt and owning lease before retrying.'}},{status:409,headers:{'Cache-Control':'no-store'}});}
      }
      if(url.pathname==='/__ops/racing/admission'&&request.method==='POST'){
        try {const input=JSON.parse(new TextDecoder().decode(await boundedBody(request,1024)));return Response.json(await env.APP.get(env.APP.idFromName('production')).racingAdmission(input),{headers:{'Cache-Control':'no-store'}});}
        catch {return Response.json({error:{code:'RACING_ADMISSION_NOT_CONFIRMED'}},{status:409});}
      }
      if(url.pathname==='/__ops/agent-auth/revoke-all'&&request.method==='POST') {
        await env.AGENT_AUTH.get(env.AGENT_AUTH.idFromName('production')).revokeAll();
        return Response.json({revoked:true},{headers:{'Cache-Control':'no-store'}});
      }
      if (url.pathname === '/__ops/company-downloads/publish' && request.method === 'POST') {
        try {
          const bytes=await boundedBody(request,4096);
          const receipt=await env.APP.get(env.APP.idFromName('production')).publishCompanyExport(JSON.parse(new TextDecoder().decode(bytes)));
          return Response.json(receipt,{headers:{'Cache-Control':'no-store'}});
        } catch {return Response.json({error:{code:'EXPORT_PUBLICATION_FAILED',message:'Publication was not confirmed. Inspect current pointers and the owning lease before retrying.'}},{status:409,headers:{'Cache-Control':'no-store'}});}
      }
      if (url.pathname === '/__ops/source-relay') return relayApprovedSource(request);
      if (url.pathname === '/__ops/source-probe' && request.method === 'GET') {
        const response=await probePublicSource(url.searchParams.get('source') || 'xpms');
        response.headers.set('X-Mcp-Release',env.RELEASE_COMMIT);return response;
      }
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
        const pack = maintenancePackForRequest(url.searchParams.get('pack') || 'backup');
        if (!['backup', 'restaurants', 'population', 'all', 'catalogue', 'resources', 'racing'].includes(pack)) return new Response('Invalid pack', {status: 400});
        return maintenanceResponse(env.APP.get(env.APP.idFromName('production')), pack, error => safeOperationError(error, env.OPS_TOKEN));
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
    const discovery = discoveryTarget(url,request.headers.get('Accept') || '');
    if (discovery.redirect) return Response.redirect(url.origin + discovery.redirect, 308);
    if (discovery.asset || url.pathname.startsWith('/assets/')) {
      const rawAsset = url.pathname.startsWith('/assets/');
      url.pathname = discovery.asset || url.pathname.slice(7);
      // Assets are selected by the public route/locale, never by an arbitrary query.
      url.search = '';
      const response = await env.ASSETS.fetch(new Request(url, request));
      const secured = new Response(response.body, response);
      if (discovery.contentType) secured.headers.set('Content-Type',discovery.contentType+'; charset=utf-8');
      if (discovery.asset) {
        secured.headers.set('Link',discoveryLinks);
        secured.headers.set('Access-Control-Allow-Origin','*');
      }
      if (discovery.page) {
        const vary=secured.headers.get('Vary');
        secured.headers.set('Vary',vary ? vary+', Accept' : 'Accept');
        secured.headers.set('Content-Language',discovery.language || 'en');
      }
      if (discovery.noindex || (rawAsset && /\.(html|json)$/.test(url.pathname))) secured.headers.set('X-Robots-Tag', 'noindex, follow');
      secured.headers.set('Content-Security-Policy', "default-src 'self'; script-src 'self' https://www.googletagmanager.com; style-src 'self' 'unsafe-inline'; connect-src 'self' https://www.google-analytics.com https://region1.google-analytics.com; img-src 'self' data: https://www.google-analytics.com https://hk.app/badges/; frame-ancestors 'none'; base-uri 'none'");
      secured.headers.set('X-Content-Type-Options', 'nosniff');
      secured.headers.set('Referrer-Policy', 'no-referrer');
      secured.headers.set('X-Mcp-Release', env.RELEASE_COMMIT);
      secured.headers.set('Strict-Transport-Security', 'max-age=31536000');
      return secured;
    }
    if (url.pathname === '/api/v1/operations') {
      const manifest = await env.BACKUPS.get('latest.json');
      return Response.json({backup: manifest ? await manifest.json() : null, maintenance: await env.APP.get(env.APP.idFromName('production')).operationsStatus(), schedules: {catalogue: 'Sunday 12:00 Asia/Hong_Kong', resources: 'every five minutes at minutes 2,7,...57; up to 256 reviews, 90 seconds, six concurrent/two per host, 50000 review attempts/day', restaurants: 'daily 10:00 Asia/Hong_Kong', population: 'Sunday 11:00 Asia/Hong_Kong', backup: 'daily 09:00 Asia/Hong_Kong'}, retentionDays: 30});
    }
    const headers = dataRequestHeaders(request);
    try {
      const response = await env.APP.get(env.APP.idFromName('production')).fetch(new Request(request, {headers}));
      return normalizeBackendResponse(response, env.RELEASE_COMMIT);
    } catch {
      return recoveringResponse(env.RELEASE_COMMIT);
    }
  },
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    const pack = scheduledPack(controller.cron);
    ctx.waitUntil(env.APP.get(env.APP.idFromName('production')).runScheduled(pack, controller.scheduledTime));
  },
} satisfies ExportedHandler<Env>;
