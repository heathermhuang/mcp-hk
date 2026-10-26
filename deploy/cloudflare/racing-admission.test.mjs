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
