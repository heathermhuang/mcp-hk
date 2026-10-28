import test from 'node:test';
import assert from 'node:assert/strict';
import {RecordFeed,feedRows} from '../../src/mcp_open_data_hk/web/record-feed.js';
const item=(id,title='Same name',identity=null)=>({id,title,identity});
test('same names and reused stock codes never establish shared identity',()=>{
 const rows=feedRows({states:{archive:{version:'a1',items:[item('1')]},official:{version:'o1',items:[item('2')]}}});assert.equal(rows.length,2);
 const grouped=feedRows({states:{archive:{version:'a1',items:[item('1','Earlier name','sfc:ce:ABC123')]},official:{version:'o1',items:[item('ABC123','Later name','sfc:ce:ABC123')]}}});
 assert.equal(grouped.length,1);assert.equal(grouped[0].variants.length,2);assert.deepEqual(grouped[0].variants.map(x=>x.version),['a1','o1']);
});
test('composite paging pins each source version and never rereads an exhausted source',async()=>{
 const calls=[];const feed=new RecordFeed(['archive','official'].map(id=>({id,async read(q,s){calls.push([id,s.cursor,s.version]);return {version:id+'-v1',items:[item(s.cursor||'first')],nextCursor:id==='archive'&&!s.cursor?'page2':null};}})));
 await feed.search({value:'Same'});assert.equal(feed.hasNext,true);assert.equal(feedRows(feed.current).length,2);
 await feed.next();assert.deepEqual(calls,[['archive',null,null],['official',null,null],['archive','page2','archive-v1']]);assert.equal(feed.hasNext,false);
 feed.previous();assert.equal(feed.index,0);assert.equal(feedRows(feed.current).length,2);
});
test('partial failure is retryable without rereading or losing the successful page',async()=>{
 let attempts=0,good=0;const feed=new RecordFeed([{id:'good',async read(){good++;return {version:'v1',items:[item('1')],nextCursor:null};}},{id:'bad',async read(){if(++attempts===1)throw Error('SOURCE_UNAVAILABLE');return {version:'v2',items:[item('2')],nextCursor:null};}}]);
 await feed.search({value:'name'});assert.equal(feed.current.states.bad.error,'SOURCE_UNAVAILABLE');assert.equal(feedRows(feed.current).length,1);
 await feed.retry();assert.equal(good,1);assert.equal(feedRows(feed.current).length,2);assert.equal(feed.current.states.bad.error,null);
});
test('version drift and nonadvancing cursors fail closed',async()=>{
 let n=0;const feed=new RecordFeed([{id:'x',async read(){return {version:++n===1?'v1':'v2',items:[item('1')],nextCursor:'next'};}}]);await feed.search({});await feed.next();assert.equal(feed.current.states.x.error,'SOURCE_SCHEMA_CHANGED');
 const repeated=new RecordFeed([{id:'x',async read(){return {version:'v1',items:[],nextCursor:'same'};}}]);await repeated.search({});await repeated.next();assert.equal(repeated.current.states.x.error,'INVALID_CURSOR');
});
test('a slow obsolete search cannot replace the current query',async()=>{
 let release;const feed=new RecordFeed([{id:'x',async read(q){if(q.value==='slow')await new Promise(r=>release=r);return {version:'v1',items:[item(q.value)],nextCursor:null};}}]);
 const pending=feed.search({value:'slow'});await feed.search({value:'fast'});release();assert.equal(await pending,null);assert.equal(feedRows(feed.current)[0].id,'fast');
});

test('shared page checkpoints retain independent versions and exclude record contents',async()=>{
 const {feedCheckpoint,readCheckpoint}=await import('../../src/mcp_open_data_hk/web/record-feed.js');
 const state={inputs:{archive:{cursor:'next',version:'a1',done:false,meta:{issuer:'webb:person:1'}},official:{cursor:null,version:'o1',done:true}},states:{archive:{version:'a1',items:[item('secret-returned-row')]},official:{version:'o1',items:[]}}};
 const checkpoint=feedCheckpoint(state,2),raw=JSON.stringify(checkpoint);assert.equal(raw.includes('secret-returned-row'),false);
 assert.deepEqual(readCheckpoint(raw,['archive','official']),checkpoint);
 for(const bad of ['{}','null',raw.replace('webb:person:1','different identity'),raw.replace('"number":2','"number":-1')])assert.equal(readCheckpoint(bad,['archive','official']),null);
});
