/** Durable source admission precedes HTTP. Container checkpoints cannot erase
 * charged attempts, unresolved requests or provider/parser holds. No source URLs,
 * user queries, credentials or page bodies are stored here. */
type Sql = {exec(query:string,...args:unknown[]):Iterable<Record<string,unknown>>};
const MAX_BODY=409600,MAX_BYTES=64*1024*1024;
export class RacingAdmission {
  private sql:Sql;
  constructor(sql:Sql){this.sql=sql;sql.exec('CREATE TABLE IF NOT EXISTS racing_admissions(id TEXT PRIMARY KEY,day INTEGER,at INTEGER,bytes INTEGER,state TEXT,code TEXT)');sql.exec('CREATE INDEX IF NOT EXISTS racing_admissions_day ON racing_admissions(day)');sql.exec("CREATE INDEX IF NOT EXISTS racing_admissions_unresolved ON racing_admissions(state) WHERE state IN ('pending','held')");sql.exec('CREATE TABLE IF NOT EXISTS racing_redirect_inspections(reference_id TEXT PRIMARY KEY,inspection_id TEXT UNIQUE NOT NULL)');}
  reserveRedirectInspection(reference:string,id:string,now=Date.now()){
    if(!/^[a-f0-9]{32}$/.test(reference)||!/^[a-f0-9]{32}$/.test(id)||reference===id)throw new Error('RACING_INSPECTION_ID');
    const held=[...this.sql.exec('SELECT state,code FROM racing_admissions WHERE id=?',reference)][0];
    if(!held||held.state!=='held'||held.code!=='DEVELOPMENT_HTTP_302')return {allowed:false,code:'RACING_INSPECTION_NOT_ELIGIBLE'};
    if([...this.sql.exec('SELECT reference_id FROM racing_redirect_inspections WHERE reference_id=?',reference)].length)return {allowed:false,code:'RACING_INSPECTION_ALREADY_ADMITTED'};
    if([...this.sql.exec('SELECT id FROM racing_admissions WHERE id=?',id)].length)return {allowed:false,code:'RACING_RESERVATION_EXISTS'};
    if([...this.sql.exec("SELECT id FROM racing_admissions WHERE state IN ('pending','held') AND id<>? LIMIT 1",reference)].length)return {allowed:false,code:'RACING_SOURCE_HELD'};
    const day=Math.floor(now/86400000),usage=[...this.sql.exec('SELECT count(*) n,coalesce(sum(bytes),0) bytes FROM racing_admissions WHERE day=?',day)][0];
    if(Number(usage.n)>=200||Number(usage.bytes)+MAX_BODY>MAX_BYTES)return {allowed:false,code:'RACING_DAILY_BUDGET'};
    this.sql.exec("INSERT INTO racing_admissions VALUES(?,?,?,?,'pending','REDIRECT_INSPECTION')",id,day,now,MAX_BODY);
    this.sql.exec('INSERT INTO racing_redirect_inspections VALUES(?,?)',reference,id);
    return {allowed:true,id,originalHoldRetained:true};
  }
  cleanup(now=Date.now()){this.sql.exec("DELETE FROM racing_admissions WHERE day<? AND state='settled'",Math.floor(now/86400000)-90);}
  reserve(id:string,now=Date.now()){
    if(!/^[a-f0-9]{32}$/.test(id))throw new Error('RACING_ADMISSION_ID');
    if([...this.sql.exec('SELECT id FROM racing_admissions WHERE id=?',id)].length)return {allowed:false,code:'RACING_RESERVATION_EXISTS'};
    if([...this.sql.exec("SELECT id FROM racing_admissions WHERE state IN ('pending','held') LIMIT 1")].length)return {allowed:false,code:'RACING_SOURCE_HELD'};
    const day=Math.floor(now/86400000),usage=[...this.sql.exec('SELECT count(*) n,coalesce(sum(bytes),0) bytes FROM racing_admissions WHERE day=?',day)][0];
    if(Number(usage.n)>=200||Number(usage.bytes)+MAX_BODY>MAX_BYTES)return {allowed:false,code:'RACING_DAILY_BUDGET'};
    this.sql.exec("INSERT INTO racing_admissions VALUES(?,?,?,?,'pending',NULL)",id,day,now,MAX_BODY);
    return {allowed:true,id};
  }
  settle(id:string,state:string,bytes:number,code:string|null){
    if(!['success','held','unknown','reviewed_parser'].includes(state)||!Number.isInteger(bytes)||bytes<0||bytes>MAX_BODY||code!==null&&!/^[A-Za-z0-9_]{1,80}$/.test(code))throw new Error('RACING_ADMISSION_SETTLEMENT');
    const row=[...this.sql.exec('SELECT state,code FROM racing_admissions WHERE id=?',id)][0];
    if(!row)throw new Error('RACING_ADMISSION_NOT_FOUND');
    if(state==='reviewed_parser'){
      if(row.state==='settled'&&['PUBLIC_RESULTS_LAYOUT_DRIFT','INVALID_RACING_ID','UNKNOWN_RESULT_CODE'].includes(String(row.code)))return {settled:true};
      if(row.state!=='held'||!['PUBLIC_RESULTS_LAYOUT_DRIFT','INVALID_RACING_ID','UNKNOWN_RESULT_CODE'].includes(String(row.code)))throw new Error('RACING_HOLD_NOT_REVIEWABLE');
    }else if(row.state!=='pending')return {settled:row.state==='settled'};
    const next=state==='success'||state==='reviewed_parser'?'settled':state==='unknown'?'pending':'held';
    this.sql.exec('UPDATE racing_admissions SET state=?,bytes=?,code=? WHERE id=?',next,bytes,code,id);
    return {settled:next==='settled'};
  }
  seed(events:{id:string;at:number;bytes:number}[],now=Date.now()){
    if(events.length>200)throw new Error('RACING_SEED_LIMIT');
    for(const e of events){
      if(!/^import-[a-f0-9]{64}$/.test(e.id)||!Number.isFinite(e.at)||e.at>now+300000||!Number.isInteger(e.bytes)||e.bytes<0||e.bytes>MAX_BODY)throw new Error('RACING_SEED_INVALID');
    }
    for(const e of events)this.sql.exec("INSERT OR IGNORE INTO racing_admissions VALUES(?,?,?,?,'settled','IMPORTED_RECEIPT')",e.id,Math.floor(e.at/86400000),e.at,e.bytes);
  }
  report(now=Date.now()){
    const day=Math.floor(now/86400000),usage=[...this.sql.exec('SELECT count(*) attempts,coalesce(sum(bytes),0) chargedBytes FROM racing_admissions WHERE day=?',day)][0];
    const unresolved=[...this.sql.exec("SELECT state,count(*) records FROM racing_admissions WHERE state IN ('pending','held') GROUP BY state")];
    return {...usage,unresolved,limits:{attempts:200,bytes:MAX_BYTES},resetsAt:new Date((day+1)*86400000).toISOString(),durable:true};
  }
  verifyProfileImport(captures:{bytes:number}[],ids:string[]){
    if(!Array.isArray(captures)||captures.length!==2||!Array.isArray(ids)||ids.length!==2||new Set(ids).size!==2)throw new Error('PROFILE_ADMISSION_REQUIRED');
    for(let i=0;i<2;i++){
      if(!/^[a-f0-9]{32}$/.test(ids[i])||!Number.isInteger(captures[i].bytes)||captures[i].bytes<1||captures[i].bytes>MAX_BODY)throw new Error('PROFILE_ADMISSION_REQUIRED');
      const row=[...this.sql.exec('SELECT state,bytes FROM racing_admissions WHERE id=?',ids[i])][0];
      if(!row||row.state!=='settled'||Number(row.bytes)!==captures[i].bytes)throw new Error('PROFILE_ADMISSION_NOT_SETTLED');
    }
  }
}
