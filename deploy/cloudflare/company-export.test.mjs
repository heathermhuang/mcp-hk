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
