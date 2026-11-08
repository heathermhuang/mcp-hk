/* Bounded discovery context is independent of typed provider query parameters. */
export function resultPath(row,state,locale){
  const params=new URLSearchParams({q:state.q||'',access:state.access||'all',provider:state.provider||'all',offset:state.offset||0,lang:locale});
  if(row.entryKind!=='connected_service'){params.set('dataset',row.id);return '/coverage?'+params;}
  if(row.packId==='catalogue'){params.set('access','sources');params.delete('dataset');return '/coverage?'+params;}
  return contextPath(row.action?.url,state,locale);
}
export function contextPath(path,state,locale){
  if(typeof path!=='string'||!/^\/(?!\/)/.test(path))throw Error('INVALID_ACTION');
  const u=new URL(path,'https://mcp.hk');if(u.origin!=='https://mcp.hk')throw Error('INVALID_ACTION');
  for(const [key,value]of Object.entries({q:state.q||'',access:state.access||'all',provider:state.provider||'all',offset:state.offset||0,lang:locale}))u.searchParams.set(key,value);
  return u.pathname+u.search+u.hash;
}
export function setSearchState(url,state){
  for(const [key,value]of Object.entries(state)){
    const omit=key==='offset'?!value:['access','provider'].includes(key)?value==='all':!value;
    if(omit)url.searchParams.delete(key);else url.searchParams.set(key,value);
  }
}
export class InventoryPages{
  constructor(){this.key=null;this.generation=null;}
  changed(key,generation,offset){
    const changed=this.key===key&&this.generation!=null&&generation!=null&&generation!==this.generation;
    this.key=key;this.generation=generation;
    return changed&&offset>0;
  }
}
