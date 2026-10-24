import {boundedBytes} from './response-policy.ts';
/** Edge-owned allocations. Unknown outcomes retain their full reservation. */
export const UPSTREAM = {calls:100, bytes:8_000_000, seconds:30, concurrency:2, active:16, globalConcurrency:12};
export const MAINTENANCE_UPSTREAM = {calls:2000, bytes:1_000_000_000, seconds:900, concurrency:6};
type Grant = {id:string;day:number;expires:number;state:string;calls:number;bytes:number;inflight:number;max_calls:number;max_bytes:number;concurrency:number;uncertain:number};
type SQL = Pick<SqlStorage,'exec'>;
type Atomic = <T>(fn:()=>T)=>T;
export class AllocationError extends Error {}

export class UpstreamStore {
  private sql:SQL;private atomic:Atomic;private dailyCalls:number;private dailyBytes:number;private clock:()=>number;
  constructor(sql:SQL,atomic:Atomic,dailyCalls:number,dailyBytes:number,clock=()=>Date.now()) {
    this.sql=sql;this.atomic=atomic;this.dailyCalls=dailyCalls;this.dailyBytes=dailyBytes;this.clock=clock;
    sql.exec('CREATE TABLE IF NOT EXISTS upstream_grants (id TEXT PRIMARY KEY, day INTEGER, expires INTEGER, state TEXT, calls INTEGER, bytes INTEGER, inflight INTEGER, max_calls INTEGER, max_bytes INTEGER, concurrency INTEGER, uncertain INTEGER)');
    sql.exec('CREATE TABLE IF NOT EXISTS upstream_daily (day INTEGER PRIMARY KEY, reserved_calls INTEGER, reserved_bytes INTEGER, observed_calls INTEGER, observed_bytes INTEGER)');
  }
  private grant(id:string):Grant {
    const row=[...this.sql.exec('SELECT * FROM upstream_grants WHERE id=?',id)][0] as Grant|undefined;
    if(!row||row.expires<=this.clock()||!['new','active'].includes(row.state))throw new AllocationError('INVALID_OPERATION');
    return row;
  }
  reserve(maintenance=false):string {
    return this.atomic(()=>{
      const now=this.clock(),day=Math.floor(now/86400000),limits=maintenance?MAINTENANCE_UPSTREAM:UPSTREAM;
      // Expired/unknown grants keep their reserved allocation; never refund on restart.
      this.sql.exec('DELETE FROM upstream_grants WHERE expires<?',now-86400000);
      this.sql.exec('DELETE FROM upstream_daily WHERE day<?',day-90);
      const active=Number([...this.sql.exec("SELECT count(*) n FROM upstream_grants WHERE expires>? AND state IN ('new','active')",now)][0]?.n||0);
      const daily=[...this.sql.exec('SELECT * FROM upstream_daily WHERE day=?',day)][0];
      if(!Number.isSafeInteger(this.dailyCalls)||!Number.isSafeInteger(this.dailyBytes)||this.dailyCalls<limits.calls||this.dailyBytes<limits.bytes||active>=UPSTREAM.active||Number(daily?.reserved_calls||0)+limits.calls>this.dailyCalls||Number(daily?.reserved_bytes||0)+limits.bytes>this.dailyBytes)throw new AllocationError('UPSTREAM_ALLOCATION_EXHAUSTED');
      const id=crypto.randomUUID();
      this.sql.exec('INSERT INTO upstream_daily VALUES (?,?,?,0,0) ON CONFLICT(day) DO UPDATE SET reserved_calls=reserved_calls+excluded.reserved_calls,reserved_bytes=reserved_bytes+excluded.reserved_bytes',day,limits.calls,limits.bytes);
      this.sql.exec('INSERT INTO upstream_grants VALUES (?,?,?,\'new\',0,0,0,?,?,?,0)',id,day,now+limits.seconds*1000,limits.calls,limits.bytes,limits.concurrency);
      return id;
    });
  }
  claim(id:string):void {
    this.atomic(()=>{const g=this.grant(id);if(g.state!=='new')throw new AllocationError('REPLAYED_OPERATION');this.sql.exec("UPDATE upstream_grants SET state='active' WHERE id=?",id);});
  }
  begin(id:string):number {
    return this.atomic(()=>{
      const g=this.grant(id),active=Number([...this.sql.exec("SELECT COALESCE(sum(inflight),0) n FROM upstream_grants WHERE expires>?",this.clock())][0]?.n||0);
      if(g.state!=='active'||g.calls>=g.max_calls||g.bytes>=g.max_bytes||g.inflight>=g.concurrency||active>=UPSTREAM.globalConcurrency)throw new AllocationError('UPSTREAM_BUDGET');
      // Charge failures before dispatch; redirects/retries must call begin again.
      this.sql.exec('UPDATE upstream_grants SET calls=calls+1,inflight=inflight+1 WHERE id=?',id);
      this.sql.exec('UPDATE upstream_daily SET observed_calls=observed_calls+1 WHERE day=?',g.day);
      return g.expires-this.clock();
    });
  }
  charge(id:string,bytes:number):void {
    const exceeded=this.atomic(()=>{
      const g=this.grant(id);
      if(!Number.isSafeInteger(bytes)||bytes<0)throw new AllocationError('INVALID_BYTES');
      this.sql.exec('UPDATE upstream_grants SET bytes=bytes+? WHERE id=?',bytes,id);
      this.sql.exec('UPDATE upstream_daily SET observed_bytes=observed_bytes+? WHERE day=?',bytes,g.day);
      return g.bytes+bytes>g.max_bytes;
    });
    if(exceeded)throw new AllocationError('UPSTREAM_BYTES');
  }
  end(id:string,uncertain=false):void {if(uncertain)this.sql.exec('UPDATE upstream_grants SET uncertain=1 WHERE id=?',id);this.sql.exec('UPDATE upstream_grants SET inflight=max(0,inflight-1) WHERE id=?',id);}
  finish(id:string,known:boolean):void {
    this.atomic(()=>{
      let g:Grant;try{g=this.grant(id);}catch{return;}
      this.sql.exec("UPDATE upstream_grants SET state='done' WHERE id=?",id);
      if(known&&g.inflight===0&&!g.uncertain)this.sql.exec('UPDATE upstream_daily SET reserved_calls=reserved_calls-?,reserved_bytes=reserved_bytes-? WHERE day=?',Math.max(0,g.max_calls-g.calls),Math.max(0,g.max_bytes-g.bytes),g.day);
    });
  }
  report() {
    return {limits:UPSTREAM,maintenance:MAINTENANCE_UPSTREAM,dailyLimits:{calls:this.dailyCalls,bytes:this.dailyBytes},daily:[...this.sql.exec('SELECT * FROM upstream_daily ORDER BY day DESC LIMIT 7')],definitions:{observed_calls:'Attempts charged before upstream dispatch, including failed connections, redirects and retries.',observed_bytes:'Decoded response body bytes observed at the edge boundary, including partial/error bodies. A terminal chunk may exceed the allocation and is cancelled. Not wire bytes or billable usage.',reserved:'Pessimistic allocations; unspent work refunded only on known completion with no in-flight requests. Unknown, cancelled or expired work retains its reservation.'}};
  }
}

export function closeOperation(response:Response,finish:(known:boolean)=>void):Response {
  const reader=response.body?.getReader();let closed=false;
  const end=(known:boolean)=>{if(!closed){closed=true;finish(known);}};
  if(!reader){end(true);return response;}
  return new Response(new ReadableStream<Uint8Array>({
    async pull(controller){try{const p=await reader.read();if(p.done){end(true);controller.close();}else controller.enqueue(p.value);}catch(e){end(false);controller.error(e);}},
    async cancel(reason){end(false);await reader.cancel(reason);},
  }),response);
}

export function upstreamTarget(raw:string):URL {
  let url:URL;try{url=new URL(raw);}catch{throw new AllocationError('UNSAFE_SOURCE');}
  const host=url.hostname.toLowerCase();
  // No IP literals, local names, credentials, fragments or nonstandard ports.
  if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.hash||url.port||!host.includes('.')||/^[\d.]+$/.test(host)||host.includes(':')||/\.(localhost|local|internal|invalid|test)$/.test(host)||/[\r\n\\]/.test(raw))throw new AllocationError('UNSAFE_SOURCE');
  return url;
}

export async function governedFetch(request:Request,store:UpstreamStore,curatedOrigin:string,curatedToken:string|undefined,fetcher:typeof fetch=fetch):Promise<Response> {
  const grant=request.headers.get('x-mcp-operation')||'',path=new URL(request.url).pathname;
  try {
    if(path==='/claim'&&request.method==='POST'){store.claim(grant);return new Response(null,{status:204});}
    if(path!=='/fetch'||!['GET','POST'].includes(request.method))throw new AllocationError('INVALID_GATEWAY_ROUTE');
    const target=upstreamTarget(request.headers.get('x-mcp-target')||'');
    const headers=new Headers({'Accept-Encoding':'identity','User-Agent':'mcp.hk-governed/1'});
    for(const name of ['accept','accept-language','if-none-match','if-modified-since','content-type']){const v=request.headers.get(name);if(v)headers.set(name,v);}
    if(target.origin===curatedOrigin&&target.pathname.startsWith('/v1/')&&curatedToken)headers.set('Authorization','Bearer '+curatedToken);
    const payload=request.method==='POST'?await boundedBytes(request,65536):undefined;
    const milliseconds=store.begin(grant),abort=new AbortController();
    const timer=setTimeout(()=>abort.abort(),milliseconds);
    let upstream:Response;
    try{upstream=await fetcher(target.href,{method:request.method,headers,redirect:'manual',body:payload,signal:abort.signal});}
    catch(error){clearTimeout(timer);store.end(grant,true);throw error;}
    let body=upstream.body;
    // identity requested; explicitly decode a source that ignores negotiation.
    const encoding=upstream.headers.get('Content-Encoding')?.toLowerCase();
    if(body&&encoding&&encoding!=='identity'){
      if(!['gzip','deflate'].includes(encoding)){await body.cancel();clearTimeout(timer);store.end(grant);throw new AllocationError('UNSUPPORTED_ENCODING');}
      body=body.pipeThrough(new DecompressionStream(encoding as 'gzip'|'deflate'));
    }
    const resultHeaders=new Headers();
    for(const name of ['content-type','etag','last-modified','location']){const v=upstream.headers.get(name);if(v)resultHeaders.set(name,v);}
    resultHeaders.set('Cache-Control','no-store');
    const reader=body?.getReader();let ended=false;
    const end=(uncertain=false)=>{if(!ended){ended=true;clearTimeout(timer);store.end(grant,uncertain);}};
    if(!reader){end();return new Response(null,{status:upstream.status,headers:resultHeaders});}
    return new Response(new ReadableStream<Uint8Array>({
      async pull(controller){try{const part=await readBeforeAbort(reader,abort.signal);if(part.done){end();controller.close();return;}store.charge(grant,part.value.length);controller.enqueue(part.value);}catch(error){abort.abort();end(true);await reader.cancel().catch(()=>{});controller.error(error);}},
      async cancel(reason){abort.abort();end(true);await reader.cancel(reason);},
    }),{status:upstream.status,headers:resultHeaders});
  }catch(error){return Response.json({error:{code:error instanceof AllocationError?error.message:'UPSTREAM_FAILURE'}},{status:error instanceof AllocationError?429:502});}
}

/** The controller's dispatch boundary, also exercised with a spy backend. */
export async function dispatchOperation(request:Request,store:UpstreamStore,backend:(request:Request)=>Promise<Response>,maintenance=false):Promise<Response> {
  let grant:string;
  try{grant=store.reserve(maintenance);}catch(error){if(error instanceof AllocationError)return Response.json({error:{code:error.message}},{status:429});throw error;}
  const headers=new Headers(request.headers);headers.set('x-mcp-operation',grant);
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),maintenance?900000:30000);
  try {
    const response=await backend(new Request(request,{headers,signal:abort.signal}));
    return closeOperation(response,known=>{clearTimeout(timer);if(!known)abort.abort();store.finish(grant,known);});
  }catch(error){clearTimeout(timer);abort.abort();store.finish(grant,false);throw error;}
}

async function readBeforeAbort(reader:ReadableStreamDefaultReader<Uint8Array>,signal:AbortSignal) {
  if(signal.aborted)throw new AllocationError('UPSTREAM_DEADLINE');
  let onAbort:()=>void=()=>{};
  const expired=new Promise<never>((_,reject)=>{onAbort=()=>reject(new AllocationError('UPSTREAM_DEADLINE'));signal.addEventListener('abort',onAbort,{once:true});});
  try{return await Promise.race([reader.read(),expired]);}finally{signal.removeEventListener('abort',onAbort);}
}
