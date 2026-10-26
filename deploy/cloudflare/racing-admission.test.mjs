import {DatabaseSync} from 'node:sqlite';
import test from 'node:test';
import assert from 'node:assert/strict';
import {RacingAdmission} from './racing-admission.ts';
const now=Date.UTC(2026,9,25,12),id=n=>n.toString(16).padStart(32,'0');
function store(){const db=new DatabaseSync(':memory:');const sql={exec(q,...v){const s=db.prepare(q);return /^SELECT/i.test(q)?s.all(...v):(s.run(...v),[]);}};return {db,sql,admission:new RacingAdmission(sql)};}
test('unknown reservations survive replacement of container/handler and UTC rollover',()=>{
 const {admission,sql}=store();assert.equal(admission.reserve(id(1),now).allowed,true);
 assert.equal(new RacingAdmission(sql).reserve(id(2),now+86400000).code,'RACING_SOURCE_HELD');
});
test('success settles bytes while all 200 attempts remain charged',()=>{
 const {admission}=store();for(let n=1;n<=200;n++){assert.equal(admission.reserve(id(n),now).allowed,true);admission.settle(id(n),'success',100,null);}
 assert.equal(admission.reserve(id(201),now).code,'RACING_DAILY_BUDGET');assert.equal(admission.report(now).attempts,200);assert.equal(admission.report(now).chargedBytes,20000);
 assert.equal(admission.reserve(id(202),now+86400000).allowed,true);
});
test('known provider denials cannot be cleared as parser fixes',()=>{
 const {admission}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'DEVELOPMENT_HTTP_403');
 assert.throws(()=>admission.settle(id(1),'reviewed_parser',409600,'DEVELOPMENT_HTTP_403'),/NOT_REVIEWABLE/);assert.equal(admission.reserve(id(2),now+86400000).allowed,false);
});
test('reviewed parser correction preserves the charge and unblocks only that known failure',()=>{
 const {admission}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'UNKNOWN_RESULT_CODE');admission.settle(id(1),'reviewed_parser',409600,'UNKNOWN_RESULT_CODE');
 assert.equal(admission.report(now).chargedBytes,409600);assert.equal(admission.reserve(id(2),now).allowed,true);
});
test('import receipts deduplicate and never erase outstanding reservations',()=>{
 const {admission}=store(),events=[{id:'import-'+'a'.repeat(64),at:now,bytes:123}];admission.seed(events,now);admission.seed(events,now);assert.equal(admission.report(now).attempts,1);
 admission.reserve(id(1),now);admission.seed(events,now);assert.equal(admission.reserve(id(2),now).code,'RACING_SOURCE_HELD');
});
test('profile imports verify two already charged completed reads without reseeding or clearing holds',()=>{
 const {admission}=store();admission.reserve(id(1),now);admission.settle(id(1),'success',100,'PROFILE_INSPECTION_COMPLETE');admission.reserve(id(2),now);admission.settle(id(2),'success',200,'PROFILE_INSPECTION_COMPLETE');
 const captures=[{bytes:100},{bytes:200}],ids=[id(1),id(2)];admission.verifyProfileImport(captures,ids);assert.equal(admission.report(now).attempts,2);
 assert.throws(()=>admission.verifyProfileImport([{bytes:101},captures[1]],ids),/NOT_SETTLED/);
 assert.throws(()=>admission.verifyProfileImport(captures,[id(1),id(1)]),/REQUIRED/);
 admission.reserve(id(3),now);admission.settle(id(3),'held',409600,'DEVELOPMENT_HTTP_302');admission.verifyProfileImport(captures,ids);assert.equal(admission.reserve(id(4),now).code,'RACING_SOURCE_HELD');
 assert.throws(()=>admission.verifyProfileImport(captures,[id(1),id(3)]),/NOT_SETTLED/);
});
test('one charged diagnostic of a known 302 retains the old hold and cannot repeat',()=>{
 const {admission,sql}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'DEVELOPMENT_HTTP_302');
 assert.equal(admission.reserveRedirectInspection(id(1),id(2),now).allowed,true);assert.equal(admission.report(now).attempts,2);
 assert.equal([...sql.exec('SELECT state FROM racing_admissions WHERE id=?',id(1))][0].state,'held');
 admission.settle(id(2),'success',90,'REDIRECT_INSPECTION_COMPLETE');
 assert.equal(admission.reserveRedirectInspection(id(1),id(3),now).code,'RACING_INSPECTION_ALREADY_ADMITTED');
 assert.equal(admission.reserve(id(4),now).code,'RACING_SOURCE_HELD');
});
test('the original collector first-settled HTTP_302 code remains eligible without being relabelled',()=>{
 const {admission,sql}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'HTTP_302');admission.settle(id(1),'held',409600,'DEVELOPMENT_HTTP_302');
 assert.equal([...sql.exec('SELECT code FROM racing_admissions WHERE id=?',id(1))][0].code,'HTTP_302');
 assert.equal(admission.reserveRedirectInspection(id(1),id(2),now).allowed,true);
 assert.equal([...sql.exec('SELECT state,code FROM racing_admissions WHERE id=?',id(1))][0].code,'HTTP_302');
});
test('diagnostics refuse denials, unknowns, other outstanding requests and quota exhaustion',()=>{
 for(const code of ['DEVELOPMENT_HTTP_403','SOURCE_HTTP_429','DEVELOPMENT_REQUEST_UNCERTAIN']){
  const {admission}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,code);assert.equal(admission.reserveRedirectInspection(id(1),id(2),now).code,'RACING_INSPECTION_NOT_ELIGIBLE');assert.equal(admission.report(now).attempts,1);
 }
 const {admission,sql}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'DEVELOPMENT_HTTP_302');sql.exec("INSERT INTO racing_admissions VALUES(?,?,?,?,'pending',NULL)",id(2),Math.floor(now/86400000),now,409600);assert.equal(admission.reserveRedirectInspection(id(1),id(3),now).code,'RACING_SOURCE_HELD');
 const full=store().admission;for(let n=1;n<200;n++){full.reserve(id(n),now);full.settle(id(n),'success',1,null);}full.reserve(id(200),now);full.settle(id(200),'held',409600,'DEVELOPMENT_HTTP_302');assert.equal(full.reserveRedirectInspection(id(200),id(201),now).code,'RACING_DAILY_BUDGET');
});
test('one routing-shape read requires the completed first diagnostic and retains the original hold',()=>{
 const {admission}=store();admission.reserve(id(1),now);admission.settle(id(1),'held',409600,'HTTP_302');
 assert.equal(admission.reserveRedirectInspection(id(1),id(2),now,true).code,'RACING_INSPECTION_PRIOR_PROOF_REQUIRED');
 admission.reserveRedirectInspection(id(1),id(2),now);assert.equal(admission.reserveRedirectInspection(id(1),id(3),now,true).code,'RACING_INSPECTION_PRIOR_PROOF_REQUIRED');
 admission.settle(id(2),'success',200,'REDIRECT_INSPECTION_COMPLETE');assert.equal(admission.reserveRedirectInspection(id(1),id(3),now,true).allowed,true);
 admission.settle(id(3),'success',200,'REDIRECT_INSPECTION_COMPLETE');assert.equal(admission.reserveRedirectInspection(id(1),id(4),now,true).code,'RACING_INSPECTION_ALREADY_ADMITTED');
 assert.equal(admission.report(now).attempts,3);assert.deepEqual(admission.report(now).unresolved.map(r=>({...r})),[{state:'held',records:1}]);assert.equal(admission.reserve(id(5),now).code,'RACING_SOURCE_HELD');
});
