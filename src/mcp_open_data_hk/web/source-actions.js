import {validateRecipe} from './playground-state.js';
const fail=()=>{throw Error('INVALID_SOURCE_ACTION');};
const same=(a,b)=>JSON.stringify(Object.entries(a||{}).sort())===JSON.stringify(Object.entries(b||{}).sort());
export function assertResource(resource,dataset,id){
  if(!resource||resource.id!==id||dataset&&resource.datasetId!==dataset)fail();
}
export function selectionAction(group,option,resource,dataset,current={}){
  assertResource(resource,dataset,resource?.id);
  const field=group?.argument,action=option?.nextAction,args=action?.arguments;
  if(!['sheet','layer','recordPath'].includes(field)||!group.options?.includes(option)||!['hk_resource_schema','hk_resource_query'].includes(action?.tool)||action.url||!args||args.resourceId!==resource.id||Object.keys(args).some(k=>!['resourceId','sheet','layer','recordPath','parameters'].includes(k))||args[field]!==option.value)fail();
  if(group.scopedToRecordPath!=null&&group.scopedToRecordPath!==(current.recordPath||''))fail();
  if(group.scopedToParameterNames&&!same(group.scopedToParameterNames.slice().sort(),Object.keys(current.parameters||{}).sort()))fail();
  if(args.parameters&&!same(args.parameters,current.parameters))fail();
  for(const key of ['sheet','layer','recordPath'])if(key!==field&&args[key]!=null&&args[key]!==current[key])fail();
  const selectors={};
  for(const key of ['sheet','layer','recordPath','parameters'])if(current[key]!=null)selectors[key]=current[key];
  selectors[field]=option.value;
  // A different parent file cannot inherit its previous child sheet.
  if(field==='recordPath'&&option.value!==current.recordPath)delete selectors.sheet;
  try{return {kind:action.tool==='hk_resource_query'?'query':'schema',selectors:validateRecipe({v:1,family:'catalogue',lang:'en',selectors}).selectors};}catch{fail();}
}
