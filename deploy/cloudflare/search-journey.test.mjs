import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resultPath,contextPath,preserveDiscoveryContext,setSearchState,InventoryPages} from '../../src/mcp_open_data_hk/web/search-journey.js';
import {assertResource,selectionAction} from '../../src/mcp_open_data_hk/web/source-actions.js';
test('literal all and Unicode remain search intent, defaults apply only to filters',()=>{
  for(const q of ['all','天氣',' school  data ','']){
    const u=new URL('https://mcp.hk/?offset=10');setSearchState(u,{q,access:'all',provider:'all',offset:0});
    assert.equal(u.searchParams.get('q'),q||null);assert.equal(u.searchParams.has('access'),false);assert.equal(u.searchParams.has('offset'),false);
  }
  const state={q:'all',access:'sources',provider:'government',offset:20},row={id:'school'};
  const path=new URL(resultPath(row,state,'zh-Hant'),'https://mcp.hk');
  for(const [k,v]of Object.entries({...state,dataset:'school',lang:'zh-Hant'}))assert.equal(path.searchParams.get(k),String(v));
  assert.equal(path.pathname,'/coverage');
  const shortcut=new URL(contextPath('/playground#p=encoded',state,'zh-Hant'),'https://mcp.hk');assert.equal(shortcut.hash,'#p=encoded');assert.equal(shortcut.searchParams.get('discoveryQ'),'all');
  const gateway=new URL(resultPath({id:'mcp:catalogue',packId:'catalogue',entryKind:'connected_service'},state,'en'),'https://mcp.hk');
  assert.equal(gateway.pathname,'/coverage');assert.equal(gateway.searchParams.get('q'),'all');assert.equal(gateway.searchParams.get('access'),'sources');
  const guided=new URL(resultPath({entryKind:'connected_service',action:{url:'/transport?operator=CTB'}},state,'en'),'https://mcp.hk');
  assert.equal(guided.searchParams.get('operator'),'CTB');assert.equal(guided.searchParams.get('discoveryQ'),'all');assert.equal(guided.searchParams.has('q'),false);
  const company=new URL(resultPath({entryKind:'connected_service',action:{url:'/companies?companySource=official'}},state,'en'),'https://mcp.hk');assert.equal(company.searchParams.get('companySource'),'official');assert.equal(company.searchParams.has('q'),false);const record=preserveDiscoveryContext(new URL('https://mcp.hk/companies?q=HSBC'),company);assert.equal(record.searchParams.get('q'),'HSBC');assert.equal(record.searchParams.get('discoveryQ'),'all');
  assert.throws(()=>resultPath({entryKind:'connected_service',action:{url:'https://elsewhere.test/'}},state,'en'));
});
test('inventory pagination resets only on a changed generation of the same search',()=>{
  const p=new InventoryPages();assert.equal(p.changed('weather','a',0),false);assert.equal(p.changed('weather','a',10),false);
  assert.equal(p.changed('weather','b',10),true);assert.equal(p.changed('weather','b',0),false);assert.equal(p.changed('school','c',20),false);
});
const resource={id:'file',datasetId:'dataset'};
function choice(field='sheet',value='2026',extra={}){
  const option={value,nextAction:{tool:'hk_resource_schema',arguments:{resourceId:'file',[field]:value,...extra}}};
  return [{argument:field,options:[option]},option];
}
test('typed choices retain selected file and caller parameters without inventing inputs',()=>{
  const current={recordPath:'reports/2026.xlsx',parameters:{date:'2026-11-08'}},[group,option]=choice('sheet','2026',{...current});
  group.scopedToRecordPath=current.recordPath;group.scopedToParameterNames=['date'];
  assert.deepEqual(selectionAction(group,option,resource,'dataset',current),{kind:'schema',selectors:{...current,sheet:'2026'}});
  assert.throws(()=>selectionAction(group,option,resource,'dataset',{recordPath:'another.xlsx',parameters:current.parameters}));
  assert.throws(()=>selectionAction(group,option,resource,'dataset',{recordPath:current.recordPath,parameters:{date:'other'}}));
  const [paths,path]=choice('recordPath','new.xlsx');
  assert.deepEqual(selectionAction(paths,path,resource,'dataset',{recordPath:'old.xlsx',sheet:'old'}).selectors,{recordPath:'new.xlsx'});
});
test('reject mismatched identities, unexpected actions, selectors and bounds',()=>{
  assert.throws(()=>assertResource(resource,'other','file'));assert.throws(()=>assertResource(resource,'dataset','other'));
  const mutations=[
    o=>o.nextAction.tool='hk_catalogue_search',o=>o.nextAction.url='/__ops/run',
    o=>o.nextAction.arguments.resourceId='other',o=>o.nextAction.arguments.limit=100,
    o=>o.nextAction.arguments.parameters={secret:'x'},o=>o.nextAction.arguments.recordPath='other.xlsx',
  ];
  for(const mutate of mutations){const [g,o]=choice();mutate(o);assert.throws(()=>selectionAction(g,o,resource,'dataset'));}
  for(const [field,value]of [['sheet',null],['sheet',''],['layer',null],['layer',-1],['layer',10001],['layer',0.1],['sheet','x'.repeat(101)],['recordPath','x'.repeat(301)]]){
    const [g,o]=choice(field,value);assert.throws(()=>selectionAction(g,o,resource,'dataset'));
  }
  const [g,o]=choice('layer',0);assert.equal(selectionAction(g,o,resource,'dataset').selectors.layer,0);
});
