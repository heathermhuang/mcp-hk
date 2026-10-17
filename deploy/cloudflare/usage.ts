/* Aggregate accounting: never persist IPs, query text, arguments or record bodies. */
export const LIMITS = {perMinute: 60, dailyRequests: 50000, dailyAddressRequests: 10000, bodyBytes: 65536, retentionDays: 90};
const CAPTURE_BYTES = 262144;
const tools = new Set(['hk_address_search','hk_address_get','hk_restaurant_search','hk_restaurant_get','hk_district_list','hk_district_statistics','hk_data_packs','hk_source_status','hk_plate_search','hk_plate_comparables','hk_plate_datasets','hk_catalogue_search','hk_dataset_resources','hk_resource_schema','hk_resource_query','hk_coverage','list_datasets','get_dataset_details','list_categories','get_category_details','search_datasets','get_supported_formats','search_datasets_with_facets','get_datasets_by_format']);
type ObjectValue = Record<string, unknown>;
const object = (v: unknown): ObjectValue => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as ObjectValue : {};
const resource = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v) ? v : '';
const dataset = (v: unknown) => typeof v === 'string' && /^[a-z0-9][a-z0-9_-]{0,159}$/.test(v) ? v : '';
export type Operation = {protocol: string; operation: string; resource: string; dataset: string; sourceCalls: number};

export function describeRequest(request: Request, body?: Uint8Array): Operation {
  const path = new URL(request.url).pathname;
  if (path === '/mcp') {
    let rpc: ObjectValue = {};
    try { rpc = object(JSON.parse(new TextDecoder().decode(body))); } catch { /* No argument text is retained. */ }
    const params = object(rpc.params), args = object(params.arguments);
    const name = typeof params.name === 'string' && tools.has(params.name) ? params.name : 'other';
    const operation = rpc.method === 'tools/call' ? name : ['initialize','tools/list','notifications/initialized','ping'].includes(String(rpc.method)) ? String(rpc.method) : 'other';
    return {protocol:'mcp', operation, resource:resource(args.resourceId), dataset:'', sourceCalls:['hk_address_search','hk_address_get'].includes(operation) ? 1 : 0};
  }
  const match = path.match(/^\/api\/v1\/resources\/([a-f0-9]{32})\/(schema|query|records)$/);
  const pack = path.match(/^\/api\/v1\/(addresses|restaurants|districts|plates)(?:\/|$)/)?.[1];
  const route = match ? 'resource_' + match[2] : pack || ({'/api/v1/coverage':'coverage','/api/v1/resources':'resource_directory','/api/v1/catalogue/datasets':'catalogue_search','/api/v1/datasets':'catalogue_search','/api/v1/packs':'packs','/api/v1/status':'status','/healthz':'health','/readyz':'readiness','/docs':'docs','/openapi.json':'openapi'}[path] || 'other');
  return {protocol:'http', operation:route, resource:match?.[1] || '', dataset:pack || '', sourceCalls:pack === 'addresses' ? 1 : 0};
}

export async function clientKey(ip: string, secret: string, now = Date.now()): Promise<string> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const digest = await crypto.subtle.sign('HMAC',key,encoder.encode(`${Math.floor(now / 86400000)}:${ip}`));
  return Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
}

export class UsageStore {
  sql: SqlStorage;
  constructor(sql: SqlStorage) {
    this.sql = sql;
    sql.exec('CREATE TABLE IF NOT EXISTS usage_daily (day INTEGER, protocol TEXT, operation TEXT, dataset TEXT, resource TEXT, status INTEGER, outcome TEXT, requests INTEGER, request_bytes INTEGER, response_bytes INTEGER, returned_items INTEGER, item_count_known INTEGER, duration_ms INTEGER, PRIMARY KEY(day,protocol,operation,dataset,resource,status,outcome))');
    sql.exec('CREATE TABLE IF NOT EXISTS rate (ip TEXT, minute INTEGER, count INTEGER, PRIMARY KEY(ip,minute))');
    sql.exec('CREATE TABLE IF NOT EXISTS daily (day INTEGER PRIMARY KEY, calls INTEGER, addresses INTEGER)');
  }
  cleanup(now = Date.now()) {
    this.sql.exec('DELETE FROM rate WHERE minute < ?',Math.floor(now/60000)-2);
    this.sql.exec('DELETE FROM daily WHERE day < ?',Math.floor(now/86400000)-2);
    this.sql.exec('DELETE FROM usage_daily WHERE day < ?',Math.floor(now/86400000)-LIMITS.retentionDays+1);
  }
  quota(key: string, sourceCalls: number, now = Date.now()) {
    const minute = Math.floor(now/60000), day = Math.floor(now/86400000), sql = this.sql;
    sql.exec('DELETE FROM rate WHERE minute < ?',minute-2);
    sql.exec('DELETE FROM daily WHERE day < ?',day-2);
    const rate = [...sql.exec<{count:number}>('SELECT count FROM rate WHERE ip=? AND minute=?',key,minute)][0]?.count || 0;
    const daily = [...sql.exec<{calls:number;addresses:number}>('SELECT calls,addresses FROM daily WHERE day=?',day)][0] || {calls:0,addresses:0};
    const dailyExceeded = daily.calls >= LIMITS.dailyRequests || daily.addresses + sourceCalls > LIMITS.dailyAddressRequests;
    const reset = dailyExceeded ? (day+1)*86400 : (minute+1)*60;
    if (rate >= LIMITS.perMinute || dailyExceeded) return {allowed:false, remaining:0, reset, retryAfter:Math.max(1,Math.ceil(reset-now/1000)), scope:dailyExceeded ? 'shared_daily_budget' : 'client_minute'};
    sql.exec('INSERT INTO rate VALUES (?,?,1) ON CONFLICT(ip,minute) DO UPDATE SET count=count+1',key,minute);
    sql.exec('INSERT INTO daily VALUES (?,1,?) ON CONFLICT(day) DO UPDATE SET calls=calls+1,addresses=addresses+excluded.addresses',day,sourceCalls);
    return {allowed:true, remaining:LIMITS.perMinute-rate-1, reset, retryAfter:0, scope:'client_minute'};
  }
  record(op: Operation, status: number, outcome: string, bytesIn: number, bytesOut: number, items: number | null, duration: number, now = Date.now()) {
    const day = Math.floor(now/86400000);
    this.sql.exec('DELETE FROM usage_daily WHERE day < ?',day-LIMITS.retentionDays+1);
    this.sql.exec('INSERT INTO usage_daily VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?) ON CONFLICT(day,protocol,operation,dataset,resource,status,outcome) DO UPDATE SET requests=requests+1,request_bytes=request_bytes+excluded.request_bytes,response_bytes=response_bytes+excluded.response_bytes,returned_items=returned_items+excluded.returned_items,item_count_known=item_count_known+excluded.item_count_known,duration_ms=duration_ms+excluded.duration_ms',day,op.protocol,op.operation,op.dataset,op.resource,status,outcome,bytesIn,bytesOut,items || 0,items === null ? 0 : 1,Math.round(duration));
  }
  report(days = 7, now = Date.now()) {
    this.cleanup(now);
    days = Math.max(1,Math.min(LIMITS.retentionDays,Math.floor(days) || 7));
    const start = Math.floor(now/86400000)-days+1;
    const rows = [...this.sql.exec('SELECT day,protocol,operation,dataset,resource,status,outcome,requests,request_bytes,response_bytes,returned_items,item_count_known,duration_ms FROM usage_daily WHERE day>=? ORDER BY day DESC,requests DESC LIMIT 5000',start)];
    const totals = [...this.sql.exec('SELECT count(*) groups,COALESCE(sum(requests),0) requests,COALESCE(sum(request_bytes),0) request_bytes,COALESCE(sum(response_bytes),0) response_bytes,COALESCE(sum(returned_items),0) returned_items,COALESCE(sum(item_count_known),0) item_count_known FROM usage_daily WHERE day>=?',start)][0];
    return {asOf:new Date(now).toISOString(),days,retentionDays:LIMITS.retentionDays,limits:LIMITS,totals,rows,rowLimit:5000,truncated:Number(totals?.groups)>rows.length,definitions:{requests:'Backend HTTP requests, including MCP protocol requests, failures and throttles. Excludes static pages/assets, private maintenance and browser Google Analytics.',response_bytes:'Uncompressed application response body bytes observed while streaming; partial bytes on cancelled/error streams. Not network wire bytes, upstream download volume or billable usage.',request_bytes:'Application request body bytes only; excludes URLs and headers.',returned_items:'Items in fully inspected successful envelopes, including catalogue metadata. Not dataset totals; item_count_known counts requests with a known returned-item count.',identity:'No visitor count or user identity is stored. Per-client quota uses a daily HMAC of the network IP; quota buckets cover up to three minutes and expired rows are pruned on backend traffic or hourly maintenance.',inspection:'Response metadata inspection is bounded to 256 KiB in memory. Larger/unparseable responses retain byte totals with unknown item count.'}};
  }
}

export function inspectResponse(raw: string, op: Operation, status: number) {
  let payload: ObjectValue = {}, inspected = false;
  try {
    const text = raw.startsWith('event:') || raw.startsWith('data:') ? raw.split('\n').find(line=>line.startsWith('data: '))?.slice(6) || '' : raw;
    payload = object(JSON.parse(text)); inspected = true;
    if (op.protocol === 'mcp') {
      const result = object(payload.result);
      if (payload.error || result.isError) return {op,outcome:'error',items:0};
      if (result.structuredContent) payload = object(result.structuredContent);
      else if (Array.isArray(result.content)) {
        try { payload = object(JSON.parse(String(object(result.content[0]).text))); } catch { payload = {}; }
      } else payload = result;
    }
  } catch { /* Bodies are neither persisted nor logged. */ }
  if (status >= 400 || payload.error) return {op,outcome:status === 429 ? 'rate_limited' : 'error',items:0};
  const resolved = object(payload.resource);
  const sourceId = Array.isArray(payload.provenance) ? object(payload.provenance[0]).sourceId : '';
  const pack = ['addresses','restaurants','population','platehk','catalogue'].includes(String(sourceId)) ? String(sourceId) : '';
  const next = {...op,dataset:dataset(resolved.datasetId) || pack || op.dataset,resource:resource(resolved.id) || op.resource};
  const data = object(payload.data);
  const items = Array.isArray(data.items) ? data.items.length : Array.isArray(payload.items) ? payload.items.length : payload.data && Array.isArray(payload.provenance) ? 1 : null;
  return {op:next,outcome:inspected ? 'ok' : 'uninspected',items};
}

export function meterResponse(response: Response, op: Operation, bytesIn: number, started: number, save: (op: Operation,status:number,outcome:string,bytesIn:number,bytesOut:number,items:number|null,duration:number)=>void) {
  const reader = response.body?.getReader();
  let total = 0, captured = 0, finished = false;
  const parts: Uint8Array[] = [];
  let resolveDone: () => void = () => {};
  const done = new Promise<void>(resolve=>{resolveDone=resolve;});
  function finish(reason?: string) {
    if (finished) return; finished = true;
    const raw = total <= CAPTURE_BYTES ? new TextDecoder().decode(concat(parts,captured)) : '';
    const result = inspectResponse(raw,op,response.status);
    try { save(result.op,response.status,reason || result.outcome,bytesIn,total,reason ? null : result.items,Date.now()-started); }
    catch { console.error(JSON.stringify({event:'usage_write_failed'})); }
    finally { resolveDone(); }
  }
  if (!reader) { finish(); return {response,done}; }
  const body = new ReadableStream<Uint8Array>({
    async pull(controller) {
      try {
        const chunk = await reader!.read();
        if (chunk.done) { finish(); controller.close(); return; }
        total += chunk.value.length;
        if (captured + chunk.value.length <= CAPTURE_BYTES) { parts.push(chunk.value.slice()); captured += chunk.value.length; }
        controller.enqueue(chunk.value);
      } catch (error) { finish('stream_error'); controller.error(error); }
    },
    async cancel(reason) { finish('cancelled'); await reader!.cancel(reason); },
  });
  return {response:new Response(body,response),done};
}

function concat(parts: Uint8Array[], length: number) { const result = new Uint8Array(length); let at=0; for(const p of parts){result.set(p,at);at+=p.length;} return result; }
