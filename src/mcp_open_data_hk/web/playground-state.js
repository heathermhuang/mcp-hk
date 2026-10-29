/* Share bounded intent only. Continuations, versions, records and credentials stay local. */
export const FAMILIES = ['catalogue','transport','addresses','restaurants','population','company_registry','enigma','hkex_daily','webb_sdi','sfc_archive','racing','platehk','seehouse'];
const fail = () => {throw Error('INVALID_RECIPE');};
const plain = v => v && typeof v === 'object' && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
const text = (v,n=300) => typeof v==='string' && v.length<=n && !/[\u0000-\u001f]/.test(v);
export function validateRecipe(v) {
  if(!plain(v) || Object.keys(v).some(k=>!['v','family','dataset','resource','selectors','filters','columns','query','view','lang'].includes(k)) || v.v!==1 || !FAMILIES.includes(v.family) || !['en','zh-Hant'].includes(v.lang)) fail();
  for(const k of ['dataset','resource']) if(v[k]!=null && (!text(v[k],200)|| !/^[\w:.-]+$/.test(v[k]))) fail();
  const selectors=v.selectors||{};
  if(!plain(selectors) || Object.keys(selectors).some(k=>!['sheet','layer','recordPath','parameters'].includes(k))) fail();
  if(selectors.sheet!=null&&!text(selectors.sheet,100)||selectors.recordPath!=null&&!text(selectors.recordPath)) fail();
  if(selectors.layer!=null&&(!Number.isInteger(selectors.layer)||selectors.layer<0||selectors.layer>10000)) fail();
  if(selectors.parameters!=null) {
    if(!plain(selectors.parameters)||Object.keys(selectors.parameters).length>10) fail();
    for(const [k,value] of Object.entries(selectors.parameters)) if(!text(k,100)||!text(value,200)||/token|secret|password|passwd|api.?key|authorization|bearer|cookie|credential|session|__proto__|constructor|prototype/i.test(k)) fail();
  }
  if(!Array.isArray(v.filters||[])||(v.filters||[]).length>10) fail();
  const used=new Set();
  for(const f of v.filters||[]) {
    if(!plain(f)||Object.keys(f).sort().join(',')!=='field,kind,value'||!text(f.field)||!f.field||used.has(f.field)||!['integer','float','string','boolean','null'].includes(f.kind)||!text(f.value,1000)) fail();
    used.add(f.field);
    if(f.kind==='integer'&&!/^-?(?:0|[1-9][0-9]{0,199})$/.test(f.value)||f.kind==='float'&&(!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(f.value)||!Number.isFinite(Number(f.value)))||f.kind==='boolean'&&!['true','false'].includes(f.value)||f.kind==='null'&&f.value!=='null') fail();
  }
  if(!Array.isArray(v.columns||[])||(v.columns||[]).length>100||new Set(v.columns||[]).size!==(v.columns||[]).length||(v.columns||[]).some(x=>!text(x)||!x)) fail();
  const query=v.query||{};
  const allowed=['value','source','issuer','district','year','operation','buildingId','quality','mode','meeting','race','profileKind','profileId','dataset','licenceType'];
  if(!plain(query)||Object.keys(query).some(k=>!allowed.includes(k))||Object.values(query).some(x=>!text(x,200))) fail();
  if(query.issuer&&!/^webb:person:[0-9]{1,12}$/.test(query.issuer)) fail();
  if(query.source&&!['all','official','archive'].includes(query.source)||query.operation&&!['search','comparables','history','building','profile'].includes(query.operation)||query.profileKind&&!['horse','jockey','trainer'].includes(query.profileKind)) fail();
  if(query.meeting&&!/^\d{4}-\d{2}-\d{2}-(?:ST|HV)$/.test(query.meeting)) fail();
  if(query.buildingId&&!/^[A-Za-z0-9][A-Za-z0-9:_-]{0,159}$/.test(query.buildingId)) fail();
  const view=v.view||{type:'table'};
  if(!plain(view)||Object.keys(view).some(k=>!['type','label','measure','unit'].includes(k))||!['table','chart'].includes(view.type)||Object.values(view).some(x=>!text(x,300))) fail();
  return structuredClone({...v,selectors,filters:v.filters||[],columns:v.columns||[],query,view});
}
export function encodeRecipe(recipe) {
  const encoded=encodeURIComponent(JSON.stringify(validateRecipe(recipe)));
  if(encoded.length>8192) throw Error('RECIPE_TOO_LARGE');
  return '#p='+encoded;
}
export function decodeRecipe(hash) {
  if(!hash) return null;
  if(!hash.startsWith('#p=')||hash.length>8195) fail();
  try{return validateRecipe(JSON.parse(decodeURIComponent(hash.slice(3))));}catch{fail();}
}
export class RequestFlow {
  constructor(){this.generation=0;}
  cancel(){this.generation++;this.controller?.abort();}
  start(){this.cancel();this.controller=new AbortController();const generation=this.generation;return {signal:this.controller.signal,current:()=>this.generation===generation};}
}
export function fieldsOf(schema){return [...new Map([...(schema?.queryFields||[]),...(schema?.fields||[])].map(f=>[f.name,f])).values()];}
export function defaultColumns(schema){if(schema?.scope==='calendar_events')return ['dtstart','summary'].filter(name=>fieldsOf(schema).some(f=>f.name===name));return fieldsOf(schema).filter(f=>f.types?.length&&f.types.every(t=>!['object','array'].includes(t))&&!f.name.startsWith('geometry.')).slice(0,8).map(f=>f.name);}
export function assertFields(recipe,schema){const names=new Set(fieldsOf(schema).map(f=>f.name));if([...recipe.columns,...recipe.filters.map(f=>f.field)].some(f=>!names.has(f)))throw Error('SAVED_FIELD_MISSING');}
