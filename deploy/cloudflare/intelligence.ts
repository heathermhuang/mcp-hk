/* Private, bounded usage intelligence. This module never receives credentials. */
import type {Operation} from './usage';

export const ANALYTICS_LIMITS = Object.freeze({perMinute:600,perDay:50000,detailRows:10000,detailDays:7,aggregateDays:90,clientDays:8,clientsPerDay:10000,dimensionsPerDay:512,keywordsPerDay:256,bytes:64*1024*1024,eventBytes:2048});
const DAY=86400000, HOUR=3600000, OFFSET=8*HOUR;
export const reportingDay=(now:number)=>Math.floor((now+OFFSET)/DAY);
const object=(v:unknown):Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v)?v as Record<string,unknown>:{};
const safeId=(v:unknown)=>typeof v==='string'&&/^[a-z0-9][a-z0-9_:.-]{0,159}$/i.test(v)?v:'';
const families=['chatgpt','claude','codex','cursor','windsurf','vscode','fastmcp','python-httpx','curl'];
function latency(rows:Row[]){
  const bins=Array.from({length:7},(_,i)=>rows.reduce((sum,row)=>sum+Number(row['b'+i]),0)),total=bins.reduce((a,b)=>a+b,0);
  const quantile=(q:number)=>{let count=0;for(let i=0;i<bins.length;i++){count+=bins[i];if(total&&count>=Math.ceil(total*q))return [100,300,1000,3000,10000,30000,null][i];}return null;};
  return {observations:total,p50UpperMs:quantile(.5),p95UpperMs:quantile(.95),overflowAboveMs:30000,note:'Bucket upper bounds on observed stream duration, including backpressure; null means no observations or >30 seconds.'};
}

export function optedOut(request:Request):boolean {
  return request.headers.get('DNT')==='1'||request.headers.get('Sec-GPC')==='1'||request.headers.get('x-mcp-analytics-opt-out')==='1'||/(?:^|;\s*)__Host-mhk_analytics=off(?:;|$)/.test(request.headers.get('Cookie')||'');
}
export function safeKeyword(value:unknown):string|null {
  if(typeof value!=='string'||value.length>160)return null;
  const term=value.normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();
  if(!term||!/^[-\p{L}\p{N} ]+$/u.test(term)||/\d{7}|(?:token|password|secret|api.?key)|[a-z0-9]{32}/i.test(term))return null;
  return term;
}
export type RequestFacts={detail:boolean;client:string;clientEvidence:string;keyword:string|null;keywordState:string;kind:string;format:string;language:string;fields:string[]};
export function requestFacts(request:Request,op:Operation,body?:Uint8Array):RequestFacts {
  let rpc:Record<string,unknown>={};
  if(body)try{rpc=object(JSON.parse(new TextDecoder().decode(body)));}catch{/* No raw text retained. */}
  const params=object(rpc.params),args=op.protocol==='mcp'?object(params.arguments):Object.fromEntries(new URL(request.url).searchParams);
  const meta=object(params._meta),info=object(params.clientInfo||meta['io.modelcontextprotocol/clientInfo']);
  const reported=typeof info.name==='string'?info.name.toLowerCase().slice(0,80):'';
  const ua=(request.headers.get('User-Agent')||'').toLowerCase().slice(0,256);
  const reportedFamily=families.find(name=>reported.includes(name)),uaFamily=families.find(name=>ua.includes(name));
  const detail=!optedOut(request),client=detail?(reportedFamily||uaFamily||'unknown'):'unknown';
  const catalogue=['hk_catalogue_search','search_datasets','search_datasets_with_facets','catalogue_search'].includes(op.operation);
  const keyword=detail&&catalogue?safeKeyword(args.q??args.query):null;
  const kind=op.operation==='other'?'unknown':/initialize|tools\/list|notifications|ping/.test(op.operation)?'protocol':/health|readiness|status|coverage|packs/.test(op.operation)?'service':catalogue?'discovery':/schema|resource_directory|dataset_resources|dataset_details|list_datasets|categories|formats/.test(op.operation)?'metadata':'data';
  const fields=Array.isArray(args.fields)?args.fields.filter((v):v is string=>typeof v==='string'&&/^[A-Za-z][A-Za-z0-9_]{0,39}$/.test(v)).slice(0,10):[];
  return {detail,client,clientEvidence:detail?(reportedFamily?'reported':uaFamily?'user_agent':'unknown'):'opted_out',keyword,keywordState:!detail?'opted_out':!catalogue?'ineligible':keyword?'retained':'withheld',kind,format:['CSV','JSON','GeoJSON','XLSX','XML'].includes(String(args.format))?String(args.format):'',language:['en','tc','sc','zh-Hant','zh-Hans'].includes(String(args.lang??args.language))?String(args.lang??args.language):'',fields:detail?fields:[]};
}

export type ResultFacts={category:string;stale:boolean;version:string;hasMore:boolean|null};
export function resultFacts(payload:Record<string,unknown>,outcome:string,status:number,items:number|null):ResultFacts {
  const code=String(object(payload.error).code||'');
  const category=outcome==='cancelled'||outcome==='stream_error'?outcome:outcome==='uninspected'?'unknown':status===429?'rate_limited':outcome==='error'?/UNSUPPORTED|NOT_QUERYABLE|NOT_SUPPORTED/.test(code)?'unsupported':/UPSTREAM|UNAVAILABLE|RECOVERING|TIMEOUT/.test(code)?'source_unavailable':'error':items===0?'no_matches':items===null?'count_unknown':'nonempty';
  const meta=object(payload.meta);
  const stale=Array.isArray(payload.warnings)&&payload.warnings.some(v=>/STALE|OUTDATED/.test(String(object(v).code||'')));
  return {category,stale,version:safeId(meta.version||meta.sourceVersion),hasMore:typeof meta.hasMore==='boolean'?meta.hasMore:null};
}
export type Observation={id:string;at:number;op:Operation;facts:RequestFacts;result:ResultFacts;status:number;outcome:string;items:number|null;bytesIn:number;bytesOut:number;duration:number};
export async function networkHash(ip:string,secret:string,at:number):Promise<string|null> {
  if(!/^[0-9a-f:.]{2,64}$/i.test(ip))return null;
  const encoder=new TextEncoder(),key=await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const result=await crypto.subtle.sign('HMAC',key,encoder.encode(`mcp.hk:usage:v1:${reportingDay(at)}:${ip}`));
  return Array.from(new Uint8Array(result),b=>b.toString(16).padStart(2,'0')).join('');
}

type Row=Record<string,SqlStorageValue>;
export class IntelligenceStore {
  private sql:Pick<SqlStorage,'exec'>;
  private transaction:<T>(fn:()=>T)=>T;
  private size:()=>number;
  constructor(sql:Pick<SqlStorage,'exec'>,transaction:<T>(fn:()=>T)=>T,size:()=>number=()=>0){
    this.sql=sql;this.transaction=transaction;this.size=size;
    sql.exec('CREATE TABLE IF NOT EXISTS ai_meta (key TEXT PRIMARY KEY,value TEXT)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_hours (hour INTEGER PRIMARY KEY,requests INTEGER,errors INTEGER,empty INTEGER,known INTEGER,bytes_in INTEGER,bytes_out INTEGER,duration INTEGER,b0 INTEGER,b1 INTEGER,b2 INTEGER,b3 INTEGER,b4 INTEGER,b5 INTEGER,b6 INTEGER)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_dimensions (day INTEGER,kind TEXT,value TEXT,requests INTEGER,errors INTEGER,empty INTEGER,PRIMARY KEY(day,kind,value))');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_keywords (day INTEGER,term TEXT,count INTEGER,error INTEGER,empty_observed INTEGER,errors_observed INTEGER,PRIMARY KEY(day,term))');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_clients (day INTEGER,hash TEXT,PRIMARY KEY(day,hash))');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_audience (day INTEGER PRIMARY KEY,clients INTEGER,unresolved INTEGER,capped INTEGER)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_seen (id TEXT PRIMARY KEY,day INTEGER)');
    sql.exec('CREATE INDEX IF NOT EXISTS ai_seen_day ON ai_seen(day)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_events (seq INTEGER PRIMARY KEY AUTOINCREMENT,at INTEGER,event TEXT)');
    sql.exec('CREATE INDEX IF NOT EXISTS ai_events_at ON ai_events(at)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_budget (day INTEGER PRIMARY KEY,minute INTEGER,minute_count INTEGER,count INTEGER,dropped INTEGER)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_digests (day INTEGER PRIMARY KEY,generated INTEGER,body TEXT)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_archives (day INTEGER PRIMARY KEY,checksum TEXT)');
    sql.exec('CREATE TABLE IF NOT EXISTS ai_archive_attempts (day INTEGER PRIMARY KEY,attempt_day INTEGER,count INTEGER)');
  }
  private rows<T=Row>(query:string,...values:SqlStorageValue[]):T[]{return [...this.sql.exec(query,...values)] as T[];}
  private n(query:string,...values:SqlStorageValue[]):number{return Number(this.rows(query,...values)[0]?.n||0);}
  private meta(key:string,value:string){this.sql.exec('INSERT INTO ai_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',key,value);}
  record(event:Observation,hash:string|null,now=Date.now()):{recorded:boolean;reason?:string}{
    if(!/^[a-f0-9-]{36}$/.test(event.id)||!Number.isFinite(event.at)||Math.abs(event.at-now)>HOUR||new TextEncoder().encode(JSON.stringify(event)).byteLength>ANALYTICS_LIMITS.eventBytes)return {recorded:false,reason:'invalid'};
    if(this.size()>ANALYTICS_LIMITS.bytes)return {recorded:false,reason:'storage_budget'};
    const day=reportingDay(event.at),budgetDay=reportingDay(now),minute=Math.floor(now/60000);
    return this.transaction(()=>{
      if(this.n('SELECT count(*) n FROM ai_seen WHERE id=?',event.id))return {recorded:false,reason:'duplicate'};
      const budget=this.rows('SELECT * FROM ai_budget WHERE day=?',budgetDay)[0];
      if(Number(budget?.count||0)>=ANALYTICS_LIMITS.perDay||Number(budget?.minute)===minute&&Number(budget?.minute_count)>=ANALYTICS_LIMITS.perMinute){
        // One bounded counter row, no identity/keyword writes for excess observations.
        this.sql.exec('UPDATE ai_budget SET dropped=dropped+1 WHERE day=?',budgetDay);return {recorded:false,reason:'write_budget'};
      }
      this.sql.exec('INSERT INTO ai_budget VALUES (?,?,1,1,0) ON CONFLICT(day) DO UPDATE SET minute_count=CASE WHEN minute=excluded.minute THEN minute_count+1 ELSE 1 END,minute=excluded.minute,count=count+1',budgetDay,minute);
      this.sql.exec('INSERT INTO ai_seen VALUES (?,?)',event.id,day);
      const hour=Math.floor(event.at/HOUR),failed=event.outcome==='ok'?0:1,empty=event.result.category==='no_matches'?1:0,known=event.items===null?0:1;
      const bucket=[100,300,1000,3000,10000,30000].findIndex(v=>event.duration<=v),bins=Array.from({length:7},(_,i)=>i===(bucket<0?6:bucket)?1:0);
      this.sql.exec('INSERT INTO ai_hours VALUES (?,1,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(hour) DO UPDATE SET requests=requests+1,errors=errors+excluded.errors,empty=empty+excluded.empty,known=known+excluded.known,bytes_in=bytes_in+excluded.bytes_in,bytes_out=bytes_out+excluded.bytes_out,duration=duration+excluded.duration,b0=b0+excluded.b0,b1=b1+excluded.b1,b2=b2+excluded.b2,b3=b3+excluded.b3,b4=b4+excluded.b4,b5=b5+excluded.b5,b6=b6+excluded.b6',hour,failed,empty,known,event.bytesIn,event.bytesOut,Math.round(event.duration),...bins);
      for(const [kind,value] of [['operation',event.op.operation],['dataset',event.op.dataset||'unknown'],['client',event.facts.client],['client_evidence',event.facts.clientEvidence],['kind',event.facts.kind],['outcome',event.result.category],['keywords',event.facts.keywordState],['freshness',event.result.stale?'stale_warning':'no_stale_warning_observed']]){
        const exists=this.n('SELECT count(*) n FROM ai_dimensions WHERE day=? AND kind=? AND value=?',day,kind,value);
        const bounded=exists||this.n("SELECT count(*) n FROM ai_dimensions WHERE day=? AND value!='overflow'",day)<ANALYTICS_LIMITS.dimensionsPerDay?value:'overflow';
        this.sql.exec('INSERT INTO ai_dimensions VALUES (?,?,?,1,?,?) ON CONFLICT(day,kind,value) DO UPDATE SET requests=requests+1,errors=errors+excluded.errors,empty=empty+excluded.empty',day,kind,bounded,failed,empty);
      }
      this.sql.exec('INSERT OR IGNORE INTO ai_audience VALUES (?,0,0,0)',day);
      if(!event.facts.detail||!hash)this.sql.exec('UPDATE ai_audience SET unresolved=unresolved+1 WHERE day=?',day);
      else if(!this.n('SELECT count(*) n FROM ai_clients WHERE day=? AND hash=?',day,hash)){
        if(this.n('SELECT count(*) n FROM ai_clients WHERE day=?',day)>=ANALYTICS_LIMITS.clientsPerDay)this.sql.exec('UPDATE ai_audience SET capped=capped+1 WHERE day=?',day);
        else {this.sql.exec('INSERT INTO ai_clients VALUES (?,?)',day,hash);this.sql.exec('UPDATE ai_audience SET clients=clients+1 WHERE day=?',day);}
      }
      if(event.facts.detail){
        this.sql.exec('INSERT INTO ai_events(at,event) VALUES (?,?)',event.at,JSON.stringify(event));
        const excess=this.n('SELECT count(*) n FROM ai_events')-ANALYTICS_LIMITS.detailRows;
        if(excess>0)this.sql.exec('DELETE FROM ai_events WHERE seq IN (SELECT seq FROM ai_events ORDER BY seq LIMIT ?)',excess);
        if(event.facts.keyword)this.keyword(day,event.facts.keyword,empty,failed);
      }
      if(!this.n("SELECT count(*) n FROM ai_meta WHERE key='collectionStart'"))this.meta('collectionStart',String(event.at));
      this.meta('lastWrite',String(now));
      return {recorded:true};
    });
  }
  private keyword(day:number,term:string,empty:number,failed:number){
    if(this.n('SELECT count(*) n FROM ai_keywords WHERE day=? AND term=?',day,term)){
      this.sql.exec('UPDATE ai_keywords SET count=count+1,empty_observed=empty_observed+?,errors_observed=errors_observed+? WHERE day=? AND term=?',empty,failed,day,term);return;
    }
    let minimum=0;
    if(this.n('SELECT count(*) n FROM ai_keywords WHERE day=?',day)>=ANALYTICS_LIMITS.keywordsPerDay){
      const victim=this.rows('SELECT term,count FROM ai_keywords WHERE day=? ORDER BY count,term LIMIT 1',day)[0];
      minimum=Number(victim.count);this.sql.exec('DELETE FROM ai_keywords WHERE day=? AND term=?',day,victim.term);
    }
    // Space-Saving: count is an upper bound; count-error is a lower bound.
    this.sql.exec('INSERT INTO ai_keywords VALUES (?,?,?,?,?,?)',day,term,minimum+1,minimum,empty,failed);
  }
  cleanup(now=Date.now()){
    const day=reportingDay(now);
    for(const [table,column,cutoff] of [['ai_hours','hour',Math.floor(now/HOUR)-90*24],['ai_dimensions','day',day-89],['ai_keywords','day',day-89],['ai_clients','day',day-7],['ai_audience','day',day-89],['ai_seen','day',day-1],['ai_budget','day',day-89],['ai_digests','day',day-89],['ai_archives','day',day-89],['ai_archive_attempts','day',day-89],['ai_events','at',now-7*DAY]] as const){
      this.sql.exec(`DELETE FROM ${table} WHERE rowid IN (SELECT rowid FROM ${table} WHERE ${column}<? LIMIT 1000)`,cutoff);
    }
  }
  report(days=7,now=Date.now()){
    days=Math.max(1,Math.min(90,Math.floor(days)||7));
    const start=reportingDay(now)-days+1,firstHour=start*24-8;
    return {schemaVersion:1,asOf:new Date(now).toISOString(),timezone:'Asia/Hong_Kong',days,limits:ANALYTICS_LIMITS,
      health:Object.fromEntries(this.rows('SELECT key,value FROM ai_meta').map(row=>[String(row.key),row.value])),
      storageBytes:this.size(),storageCircuitOpen:this.size()>ANALYTICS_LIMITS.bytes,
      latency:latency(this.rows('SELECT * FROM ai_hours WHERE hour>=?',firstHour)),
      comparison:this.comparison(now),
      totals:this.rows('SELECT COALESCE(sum(requests),0) requests,COALESCE(sum(errors),0) errors,COALESCE(sum(empty),0) empty,COALESCE(sum(known),0) known_item_counts,COALESCE(sum(bytes_out),0) response_bytes FROM ai_hours WHERE hour>=?',firstHour)[0],
      hours:this.rows('SELECT * FROM ai_hours WHERE hour>=? ORDER BY hour',firstHour),
      dimensionsTruncated:this.n('SELECT count(*) n FROM (SELECT kind,value FROM ai_dimensions WHERE day>=? GROUP BY kind,value)',start)>512,
      dimensions:this.rows('SELECT kind,value,sum(requests) requests,sum(errors) errors,sum(empty) empty FROM ai_dimensions WHERE day>=? GROUP BY kind,value ORDER BY requests DESC LIMIT 512',start),
      audience:this.rows('SELECT * FROM ai_audience WHERE day>=? ORDER BY day',start),
      keywords:this.rows('SELECT term,sum(count) upper_bound,sum(count-error) lower_bound,sum(empty_observed) empty_observed,sum(errors_observed) errors_observed FROM ai_keywords WHERE day>=? GROUP BY term ORDER BY lower_bound DESC LIMIT 50',start),
      recent:this.rows('SELECT event FROM ai_events WHERE at>=? ORDER BY seq DESC LIMIT 50',start*DAY-OFFSET).map(row=>JSON.parse(String(row.event))),
      budget:this.rows('SELECT day,count,dropped FROM ai_budget WHERE day>=? ORDER BY day',start),
      archives:this.rows('SELECT * FROM ai_archives ORDER BY day DESC LIMIT 14'),
      archiveAttempts:this.rows('SELECT * FROM ai_archive_attempts ORDER BY day DESC LIMIT 14'),
      digests:this.rows('SELECT day,generated,body FROM ai_digests ORDER BY day DESC LIMIT 14').map(row=>({...row,body:JSON.parse(String(row.body))})),
      definitions:{scope:'Completed admitted backend requests observed within collection budgets. Legacy /__ops/usage includes throttles; detailed analytics excludes 429 and unobserved/unfinished streams.',audience:'Daily network estimates, never people. Shared gateways merge people; missing/opted-out identities are unresolved. Do not sum daily counts to infer weekly/monthly uniques.',keywords:'Space-Saving approximate demand. Bounds cover retained daily candidates; a term evicted on another day can have additional unrepresented occurrences. Empty/error counts are observations while tracked, not estimated rates.',delivery:'Digests are generated privately. No external notification destination is configured.',detail:'Recent detail is bounded by seven days and 10,000 rows, whichever is shorter. No pre-release backfill.'}};
  }
  private comparison(now:number){
    const today=reportingDay(now),started=Number(this.rows("SELECT value FROM ai_meta WHERE key='collectionStart'")[0]?.value||now);
    const windows=[{name:'lastSevenCompletedDays',start:today-7,end:today},{name:'previousSevenCompletedDays',start:today-14,end:today-7}].map(window=>{
      const counts=this.rows('SELECT COALESCE(sum(requests),0) requests,COALESCE(sum(errors),0) errors,COALESCE(sum(empty),0) empty FROM ai_hours WHERE hour>=? AND hour<?',window.start*24-8,window.end*24-8)[0];
      return {...window,...counts,baselineAvailable:started<=window.start*DAY-OFFSET};
    });
    return {windows,note:'Completed HK calendar days only. Daily network estimates are never summed into weekly people. Collection budgets/outages still limit coverage.'};
  }
  digest(now=Date.now()){
    // Existing five-minute ticks, after 09:00 HK; one bounded day per invocation.
    if(((now+OFFSET)%DAY)<9*HOUR)return {generated:false,reason:'not_due'};
    const today=reportingDay(now),last=this.rows('SELECT max(day) day FROM ai_digests')[0]?.day;
    const started=Number(this.rows("SELECT value FROM ai_meta WHERE key='collectionStart'")[0]?.value||now);
    const day=last===null||last===undefined?Math.max(today-7,reportingDay(started)):Math.max(today-7,Number(last)+1);
    if(day>=today)return {generated:false,reason:'current'};
    const hours=this.rows('SELECT * FROM ai_hours WHERE hour>=? AND hour<? ORDER BY hour',day*24-8,(day+1)*24-8);
    const totals=hours.reduce<{requests:number;errors:number;empty:number}>((a,r)=>({requests:a.requests+Number(r.requests),errors:a.errors+Number(r.errors),empty:a.empty+Number(r.empty)}),{requests:0,errors:0,empty:0});
    const keywords=this.rows('SELECT term,count upper_bound,count-error lower_bound,empty_observed FROM ai_keywords WHERE day=? ORDER BY count-error DESC LIMIT 10',day);
    const previous=this.rows('SELECT COALESCE(sum(requests),0) requests FROM ai_hours WHERE hour>=? AND hour<?',(day-1)*24-8,day*24-8)[0];
    const baselineAvailable=started<=(day-1)*DAY-OFFSET;
    const body={schemaVersion:1,day,periodStart:new Date(day*DAY-OFFSET).toISOString(),periodEnd:new Date((day+1)*DAY-OFFSET).toISOString(),totals,latency:latency(hours),comparison:{baselineAvailable,previousRequests:Number(previous.requests),requestChangePercent:baselineAvailable&&Number(previous.requests)>0?100*(totals.requests-Number(previous.requests))/Number(previous.requests):null},audience:this.rows('SELECT * FROM ai_audience WHERE day=?',day)[0]||null,topDatasets:this.rows("SELECT value,requests,errors,empty FROM ai_dimensions WHERE day=? AND kind='dataset' ORDER BY requests DESC LIMIT 10",day),keywords,collectionStarted:new Date(started).toISOString(),partial:started>day*DAY-OFFSET,notification:{status:'not_configured',destination:null}};
    this.sql.exec('INSERT OR IGNORE INTO ai_digests VALUES (?,?,?)',day,now,JSON.stringify(body));
    return {generated:true,day};
  }
  nextArchive(now=Date.now()){
    const today=reportingDay(now);
    const row=this.rows('SELECT d.day,d.body FROM ai_digests d LEFT JOIN ai_archive_attempts a ON d.day=a.day WHERE d.day NOT IN (SELECT day FROM ai_archives) AND (a.day IS NULL OR a.attempt_day!=? OR a.count<3) ORDER BY d.day LIMIT 1',today)[0];
    if(!row)return null;
    const day=Number(row.day);
    this.sql.exec('INSERT INTO ai_archive_attempts VALUES (?,?,1) ON CONFLICT(day) DO UPDATE SET count=CASE WHEN attempt_day=excluded.attempt_day THEN count+1 ELSE 1 END,attempt_day=excluded.attempt_day',day,today);
    return {schemaVersion:1,day,digest:JSON.parse(String(row.body)),tables:{
      ai_hours:this.rows('SELECT * FROM ai_hours WHERE hour>=? AND hour<? ORDER BY hour',day*24-8,(day+1)*24-8),
      ai_dimensions:this.rows('SELECT * FROM ai_dimensions WHERE day=? ORDER BY kind,value',day),
      ai_keywords:this.rows('SELECT * FROM ai_keywords WHERE day=? ORDER BY term',day),
      ai_audience:this.rows('SELECT * FROM ai_audience WHERE day=?',day),
      ai_budget:this.rows('SELECT * FROM ai_budget WHERE day=?',day),
    }};
  }
  confirmArchive(day:number,checksum:string){
    if(!/^[a-f0-9]{64}$/.test(checksum)||!this.n('SELECT count(*) n FROM ai_digests WHERE day=?',day))throw Error('INVALID_ARCHIVE_RECEIPT');
    this.sql.exec('INSERT OR IGNORE INTO ai_archives VALUES (?,?)',day,checksum);
  }
}

export async function archiveClosedDay(bucket:R2Bucket,snapshot:ReturnType<IntelligenceStore['nextArchive']>,now:number){
  if(!snapshot)return null;
  const raw=JSON.stringify(snapshot),bytes=new TextEncoder().encode(raw);
  if(bytes.length>524288)throw Error('ANALYTICS_ARCHIVE_TOO_LARGE');
  const digest=async(value:Uint8Array)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',value)),b=>b.toString(16).padStart(2,'0')).join('');
  const checksum=await digest(bytes),date=new Date(snapshot.day*DAY).toISOString().slice(0,10),key=`usage/daily/${date}.json`;
  await bucket.put(key,bytes,{customMetadata:{sha256:checksum},httpMetadata:{contentType:'application/json'}});
  const saved=await bucket.get(key);
  if(!saved||saved.size>524288||await digest(new Uint8Array(await saved.arrayBuffer()))!==checksum)throw Error('ANALYTICS_ARCHIVE_NOT_VERIFIED');
  const old=await bucket.list({prefix:'usage/daily/',limit:100});
  const cutoff=new Date((reportingDay(now)-89)*DAY).toISOString().slice(0,10);
  const expired=old.objects.filter(v=>/^usage\/daily\/\d{4}-\d{2}-\d{2}\.json$/.test(v.key)&&v.key.slice(12,22)<cutoff).map(v=>v.key);
  if(expired.length)await bucket.delete(expired);
  return {day:snapshot.day,checksum};
}
