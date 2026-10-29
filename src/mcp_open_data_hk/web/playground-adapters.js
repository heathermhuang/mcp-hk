/* Small explicit family registry over existing read-only services. */
import {fetchPublicJson} from './http.js';
import {RecordFeed,feedRows} from './record-feed.js';
import {recordSources} from './record-sources.js';
import {parseExact,wirePresentation,exactJson} from './playground-wire.js';
export const genericFamily = family => ['catalogue','transport'].includes(family);
export const url = (base,args={}) => base+'?'+new URLSearchParams(Object.entries(args).filter(([,v])=>v!=null&&v!==''));
export async function request(base,args,signal,body){
  let wire;const path=args?url(base,args):base;
  const p=await fetchPublicJson(path,body,{signal,capture:raw=>wire=raw});
  Object.defineProperties(p,{wire:{value:wire},request:{value:{path,body}}});return p;
}
function exactRows(p,rows){
  if(!p.wire)throw Error('EXACT_RESPONSE_REQUIRED');
  const d=parseExact(p.wire).data;
  if(Array.isArray(d))return d;
  for(const key of ['items','candidates','results','listings','events'])if(Array.isArray(d?.[key])&&rows===p.data[key])return d[key];
  return rows.length===1&&rows[0]===p.data?[d]:[];
}
function result(p,rows,{next=null,actions=[],columns,chart,exportUrl=null,exportKind=null}={}){
  if(!Array.isArray(rows)||rows.length>100)throw Error('INVALID_SOURCE_PAGE');
  const exact=exactRows(p,rows);
  if(exact.length!==rows.length)throw Error('SOURCE_SCHEMA_CHANGED');
  columns=columns||[...new Set(rows.flatMap(Object.keys))].filter(k=>rows.some(r=>r[k]===null||typeof r[k]!=='object')).slice(0,8);
  actions=rows.map((row,i)=>actions[i]||{kind:'captured',wire:'{"data":'+exactJson(exact[i])+',"meta":'+JSON.stringify(p.meta||{})+'}'});
  return {rows,presentation:wirePresentation(exact,columns),envelopes:[p],total:p.meta?.total??null,next,actions,chart,exportUrl,exportKind,errors:[],version:p.meta?.version||p.meta?.snapshotId||null};
}
export class DomainSession {
  constructor(family,locale=()=> 'en'){
    this.family=family;this.locale=locale;
    this.sources=recordSources((base,args,signal)=>request(base,args,signal||this.signal),locale);
  }
  cancel(){this.feed?.cancel();}
  async choices(signal){
    if(this.family==='population'||this.family==='restaurants')return {districts:(await request('/api/v1/districts',null,signal)).items};
    if(this.family==='racing'){this.meetings=(await request('/api/v1/racing/meetings',{limit:100},signal)).data.items;return {meetings:this.meetings};}
    return {};
  }
  async read(recipe,signal,{next=false,retry=false}={}){
    this.signal=signal;const q=recipe.query,f=this.family,lang=this.locale();
    if(['company_registry','enigma','hkex_daily','webb_sdi','sfc_archive'].includes(f)){
      const group=['company_registry','enigma'].includes(f)?'companies':f==='sfc_archive'?'sfc':'hkex';
      let sources=this.sources[group];
      const choose=q.source|| (f==='enigma'?'archive':f==='hkex_daily'?'official':f==='webb_sdi'?'archive':'all');
      sources=sources.filter(s=>choose==='all'||choose==='archive'&&/archive/.test(s.id)||choose==='official'&&!/archive/.test(s.id));
      if(!next&&!retry){this.feed?.cancel();this.feed=new RecordFeed(sources);await this.feed.search({value:group==='hkex'?q.value.padStart(5,'0'):group==='sfc'?q.value.toUpperCase():q.value,issuer:q.issuer});}
      else if(retry)await this.feed.retry();else await this.feed.next();
      // Bounded retained pages. Previous returns the captured source page; never replays cursors against newer data.
      while(this.feed.pages.length>3){this.feed.pages.shift();this.feed.index--;}
      return this.feedResult();
    }
    let p,rows,actions=[],options={};
    if(f==='addresses'){
      p=await request('/api/v1/addresses/search',{q:q.value,limit:10},signal);rows=p.data.items;
      actions=rows.map(r=>({kind:'address',id:r.id}));
    }else if(f==='restaurants'){
      p=await request('/api/v1/restaurants',{q:q.value||'',district:q.district,licenceType:q.licenceType,limit:20,lang,cursor:next?this.current?.next:null},signal);rows=p.data.items;
      actions=rows.map(r=>({kind:'restaurant',id:r.id}));options.next=p.meta?.nextCursor;
    }else if(f==='population'){
      if(!q.district)throw Error('DISTRICT_REQUIRED');
      p=await request('/api/v1/districts/'+encodeURIComponent(q.district)+'/statistics',{year:q.year},signal);rows=[p.data];
      options.chart={label:'districtId',measure:'population',unit:'persons'};
    }else if(f==='platehk'){
      const operation=q.operation==='comparables'?'comparables':'search';
      p=await request('/api/v1/plates/'+operation,{q:q.value,page:next?this.current?.next:1,pageSize:20,...(operation==='search'?{dataset:q.dataset||'all',mode:q.mode||'exact',sort:'date_desc'}:{})},signal);rows=p.data.items;
      options.next=p.data.nextPage||null;options.chart={label:'single_line',measure:'amount_hkd',unit:'HKD (historical auction amount)'};
      options.columns=['single_line','auction_date_label','amount_hkd','result_status','dataset_key','auction_key'];
    }else if(f==='seehouse'){
      const operation=q.operation==='history'?'price-history':q.buildingId?'building':'search';
      p=await request('/api/v1/properties/'+operation,{...(q.buildingId?{buildingId:q.buildingId}:{q:q.value,limit:10}),...(operation==='building'?{quality:q.quality||'current'}:{}),lang},signal);
      rows=operation==='search'?p.data.candidates:operation==='building'?p.data.listings:p.data.events;
      actions=rows.map(r=>operation==='search'?{kind:'building',id:r.id}:null);
    }else if(f==='racing'){
      const meeting=this.meetings?.find(m=>m.meeting.id===q.meeting);
      if(!q.profileId&&!meeting)throw Error('SAVED_MEETING_MISSING');
      const version=meeting?.version;
      if(q.profileId){
        const status=await request('/api/v1/racing/status',null,signal),capability=status.data?.profileObservations;
        if(!capability?.available||!capability.modes?.rest||!capability.modes?.browser)throw Error('PROFILE_BROWSER_NOT_ACTIVATED');
        const cursor=next?this.current?.next:null;
        const base='/api/v1/racing/profiles/'+encodeURIComponent(q.profileKind||'horse')+'/'+encodeURIComponent(q.profileId);
        p=await request(base+(q.operation==='history'?'/history':''),{language:lang==='zh-Hant'?'zhHant':'en',limit:q.operation==='history'?20:null,cursor,version:next?this.current?.version:null},signal);
        rows=Array.isArray(p.data?.items)?p.data.items:[p.data];options.next=p.meta?.nextCursor;if(q.operation==='history'&&capability.modes?.export){options.exportUrl=url(base+'/export',{version:p.meta.version,language:lang==='zh-Hant'?'zhHant':'en',limit:20,cursor});options.exportKind='profile';}
      }else if(q.race){
        p=await request('/api/v1/racing/races/'+encodeURIComponent(q.race)+'/results',{version},signal);rows=p.data.results;
        options.columns=['placingRaw','horseNumber','horse','jockey','trainer','draw','timeSeconds','winOddsFinal'];
        const tree=parseExact(p.wire).data.results;
        const out={rows,presentation:wirePresentation(tree,options.columns),envelopes:[p],total:null,next:null,errors:[],actions:rows.map(r=>({kind:'participant',id:r.horse.id,version})),exportKind:'race',exportUrl:url('/api/v1/racing/exports',{version,raceId:q.race}),version};
        this.current=out;return out;
      }else{
        p=await request('/api/v1/racing/races',{version},signal);rows=p.data.items;actions=rows.map(r=>({kind:'race',id:r.id}));
      }
    }else throw Error('UNSUPPORTED_FAMILY');
    const out=result(p,rows,{...options,actions});this.current=out;return out;
  }
  feedResult(){
    const page=this.feed.current,items=feedRows(page,this.locale()).flatMap(row=>row.variants),rows=[],exact=[],envelopes=[];
    for(const [id,s] of Object.entries(page.states))if(s.items?.length&&s.meta?.envelope)envelopes.push(s.meta.envelope);
    for(const item of items){
      const source=page.states[item.source],p=source.meta.envelope,index=p.data.items?.indexOf(item.raw)??-1;
      const parsed=parseExact(p.wire).data;const tree=Array.isArray(parsed?.items)?parsed.items[index]:parsed;
      rows.push({source:item.source,version:item.version,...item.raw});exact.push({source:item.source,version:item.version,...tree});
    }
    const columns=['source',...new Set(rows.flatMap(Object.keys).filter(k=>!['source','version'].includes(k)))].slice(0,8);
    const out={rows,items,presentation:wirePresentation(exact,columns),envelopes,total:null,next:this.feed.hasNext,errors:Object.entries(page.states).filter(([,s])=>s.error).map(([source,s])=>({source,message:s.error})),actions:items.map(item=>({kind:item.issuerChoice?'issuer':'entity',item})),version:null};this.current=out;return out;
  }
  previous(){if(!this.feed||this.feed.index<1)return null;this.feed.previous();return this.feedResult();}
  async detail(action,signal){
    this.signal=signal;
    if(action.kind==='captured')return {envelopes:[Object.assign(JSON.parse(action.wire),{wire:action.wire})]};
    if(action.kind==='entity'){
      const row=action.item,source=this.sources[['company_registry','enigma'].includes(this.family)?'companies':this.family==='sfc_archive'?'sfc':'hkex'].find(s=>s.id===row.source);
      const p=await source.detail(row);
      if(p.meta?.version!==row.version||String(p.data?.entity_id??p.data?.ce??p.data?.id)!==String(row.id))throw Error('SOURCE_IDENTITY_CHANGED');
      const families=row.source==='company-archive'?['names','officers','licences','licence_relationships']:row.source==='company-observations'?['addresses']:row.source==='licence-archive'?['licences','licence_relationships']:row.source==='licence-observations'&&this.feed.current?.states[row.source]?.meta?.capability?.historyAvailable?['history']:[];
      return {envelopes:[p],history:families.length?{id:row.id,version:row.version,view:row.source==='company-observations'?'latest_observed':'archive',kind:row.source==='licence-observations'?'sfc':'company',families}:null};
    }
    const base=action.kind==='address'?'/api/v1/addresses/':action.kind==='restaurant'?'/api/v1/restaurants/':'/api/v1/racing/participants/';
    return {envelopes:[await request(base+encodeURIComponent(action.id),action.version?{version:action.version}:null,signal)]};
  }
  async history(context,family,cursor,signal){
    if(context.kind==='sfc')return request('/api/v1/sfc/corporations/'+encodeURIComponent(context.id)+'/history',{version:context.version,limit:20,cursor},signal);
    return request('/api/v1/companies/'+encodeURIComponent(context.id)+'/'+family,{version:context.version,view:context.view,limit:20,cursor},signal);
  }
}
// Examples describe the actual applied request. Tools can be unavailable when a
// source has not activated MCP; the public source gate still controls each call.
export function mcpExample(requestInfo){
  if(!requestInfo)return null;const u=new URL(requestInfo.path,'https://mcp.hk'),args=Object.fromEntries(u.searchParams),path=u.pathname;
  const tools={'/api/v1/companies':'hk_company_search','/api/v1/addresses/search':'hk_address_search','/api/v1/restaurants':'hk_restaurant_search','/api/v1/plates/search':'hk_plate_search','/api/v1/plates/comparables':'hk_plate_comparables','/api/v1/properties/search':'hk_property_search','/api/v1/properties/building':'hk_property_building','/api/v1/properties/price-history':'hk_property_price_history','/api/v1/hkex/latest/disclosures':'hk_hkex_latest_disclosures','/api/v1/hkex/archive/issuers':'hk_hkex_archive_issuers','/api/v1/hkex/archive/disclosures':'hk_hkex_archive_disclosures','/api/v1/racing/races':'hk_racing_search'};
  let tool=tools[path];
  for(const key of ['limit','page','pageSize','year'])if(args[key])args[key]=Number(args[key]);
  const district=path.match(/^\/api\/v1\/districts\/([^/]+)\/statistics$/);if(district){tool='hk_district_statistics';args.districtId=decodeURIComponent(district[1]);}
  const race=path.match(/^\/api\/v1\/racing\/races\/([^/]+)\/results$/);if(race){tool='hk_racing_results';args.raceId=decodeURIComponent(race[1]);}
  const profile=path.match(/^\/api\/v1\/racing\/profiles\/([^/]+)\/([^/]+)(\/history)?$/);if(profile){tool=profile[3]?'hk_racing_profile_history':'hk_racing_profile_observation';args.kind=decodeURIComponent(profile[1]);args.sourceId=decodeURIComponent(profile[2]);if(!profile[3]){delete args.language;delete args.limit;}}
  return tool?tool+'('+JSON.stringify(args,null,2)+')':null;
}
