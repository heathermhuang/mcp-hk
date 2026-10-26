import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {pagePackage,csvCell} from '../../src/mcp_open_data_hk/web/company-export.js';

test('displayed-page ZIP is readable by an independent ZIP/CSV reader and hashes its actual Unicode bytes',async()=>{
 const rows=[{entity_id:12,name:'香港,"甲"\n公司',id:'0000123',formula:' \t=HYPERLINK("x")',amount:-12,unknown:null,scope:['hk_domicile']},{entity_id:13,name:'ＦＯＯ',id:'123',formula:'@SUM(A1)',amount:0,unknown:'',scope:[]}];
 const envelope={data:{items:rows},meta:{version:'archive-v1',nextCursor:'signed'},provenance:[{view:'archive'}],warnings:[]};
 const pack=await pagePackage(envelope,{family:'search',page:2},'David Webb original notice\n');
 assert.equal(pack.manifest.scope,'this_page');assert.equal(pack.manifest.rowCount,2);assert.match(pack.sha256,/^[a-f0-9]{64}$/);
 const dir=mkdtempSync(join(tmpdir(),'company-page-'));
 try{
  const zip=join(dir,'page.zip');writeFileSync(zip,new Uint8Array(await pack.blob.arrayBuffer()));
  const probe=spawnSync('python3',['-c',`import sys,zipfile,json,hashlib,csv,io
p=sys.argv[1]
assert hashlib.sha256(open(p,'rb').read()).hexdigest()==sys.argv[2]
with zipfile.ZipFile(p) as z:
 assert z.testzip() is None
 m=json.loads(z.read('manifest.json'));assert m['scope']=='this_page' and m['rowCount']==2
 for f in m['files']:
  b=z.read(f['file']);assert len(b)==f['bytes'] and hashlib.sha256(b).hexdigest()==f['sha256']
 r=json.loads(z.read('records.json'));assert r[0]['id']=='0000123' and r[0]['amount']==-12 and r[0]['unknown'] is None and r[0]['scope']==['hk_domicile']
 c=list(csv.DictReader(io.StringIO(z.read('records.csv').decode('utf-8-sig'))));assert len(c)==2 and c[0]['name']==r[0]['name'] and c[0]['id']=="'0000123" and c[0]['formula'].startswith("'") and c[1]['formula'].startswith("'") and c[0]['amount']=='-12'
 assert b'Webb' in z.read('NOTICE.txt')`,zip,pack.sha256],{encoding:'utf8'});assert.equal(probe.status,0,probe.stderr);
 }finally{rmSync(dir,{recursive:true,force:true});}
 assert.equal(csvCell('-0001'),`"'-0001"`);assert.equal(csvCell(-1),'"-1"');
});
test('empty or unversioned data cannot become a successful page export',async()=>{
 for(const payload of [{data:{items:[]},meta:{version:'x'}},{data:{items:[{}]},meta:{version:'../secret'}}])await assert.rejects(pagePackage(payload,{family:'search'},'Webb'));
});

test('relationship display preserves given names and source Chinese names without treating organisation alternatives as given names',async()=>{
 const {partyNames}=await import('../../src/mcp_open_data_hk/web/company-fields.js');
 const person={kind:'person',name1:'Kadoorie',name2:'Michael David',chineseName:'米高嘉道理'};
 assert.deepEqual(partyNames(person,'en'),{primary:'Kadoorie, Michael David',secondary:'米高嘉道理'});
 assert.deepEqual(partyNames(person,'zh'),{primary:'米高嘉道理',secondary:'Kadoorie, Michael David'});
 assert.notEqual(partyNames({kind:'person',name1:'CHAN',name2:'Tai Man'}).primary,partyNames({kind:'person',name1:'CHAN',name2:'Wai Man'}).primary);
 assert.equal(partyNames({kind:'organisation',name1:'Company Limited',name2:'Alternative'}).primary,'Company Limited');
 assert.equal(partyNames({kind:'person',name1:'CHAN',name2:null}).primary,'CHAN');
});

test('official page exports retain their separate view and Registry attribution',async()=>{
  const payload={meta:{version:'official-'+'a'.repeat(32),view:'latest_observed'},data:{items:[{entity_id:'cr:local:00001234',name1:'Raw Company',identifier:{namespace:'cr:local:brn',value:'00001234'}}]},provenance:[{attribution:'Companies Registry',sourceUrl:'https://www.cr.gov.hk/'}],warnings:[]};
  const pack=await pagePackage(payload,{family:'official-search'},'Government of the HKSAR / Companies Registry / DATA.GOV.HK');
  assert.equal(pack.manifest.view,'latest_observed');assert.equal(pack.manifest.scope,'this_page');assert.equal(pack.manifest.currentVerification,false);assert.equal(pack.manifest.rowCount,1);
  await assert.rejects(pagePackage(payload,{},'Webb archive notice'));
});

test('grouped exports label organisation rows and retain only displayed name evidence',async()=>{
 const payload={data:{items:[{entity_id:1,name1:'Same name',matched_fact_count:50,matched_names:[{display_name:'Former name',fact_id:'name-1'}]},{entity_id:2,name1:'Same name',matched_fact_count:1,matched_names:[]}]},meta:{version:'grouped-v1',view:'archive',groupBy:'organisation'},provenance:[{view:'archive'}],warnings:[]};
 const pack=await pagePackage(payload,{family:'search',groupBy:'organisation'},'David Webb original notice');
 assert.equal(pack.manifest.rowCount,2);assert.equal(pack.manifest.scope,'this_page');assert.equal(pack.manifest.selection.groupBy,'organisation');
 const bytes=Buffer.from(await pack.blob.arrayBuffer());assert.ok(bytes.includes(Buffer.from('matched_fact_count')));assert.ok(bytes.includes(Buffer.from('Former name')));
});
test('HKEX summary page exports retain their own view and never infer a data licence',async()=>{
 const e={data:{items:[{stock_code:'00005',filed_date:null,shares:'9007199254740993.00000001'}]},meta:{version:'hkex-daily-'+'a'.repeat(32),view:'hkex_daily_summary'},provenance:[{sourceId:'hkex_daily_summary',licenceClaimed:false}],warnings:[]};
 const p=await pagePackage(e,{family:'daily-disclosures'},'Source: Hong Kong Exchanges and Clearing Limited (HKEX). No licence grant is asserted.');
 assert.equal(p.manifest.view,'hkex_daily_summary');assert.equal(p.manifest.rowCount,1);
 await assert.rejects(pagePackage(e,{},'Webb archive reuse notice'));
 await assert.rejects(pagePackage({...e,meta:{...e.meta,view:'unknown'}},{},'Webb notice'));
});
