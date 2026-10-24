import {fetchPublicJson} from './http.js';
import {pagePackage} from './company-export.js';
import {partyNames} from './company-fields.js';

const $=id=>document.getElementById(id),t=(...args)=>MhkI18n.t(...args),api=fetchPublicJson;
const families={overview:'companyOverview',names:'companyNames',officers:'companyOfficers',licences:'companyLicences',licence_relationships:'companyRelations'};
let searchGeneration=0,recordGeneration=0,factGeneration=0,snapshotGeneration=0;
let submitted=null,searchResult=null,detail=null,facts=null,snapshot=null;
let searchError=null,recordError=null,factError=null,searchBusy=false,recordBusy=false,factBusy=false;
let selectedId=null,selectedVersion=null,family='overview',searchCursor=null,factCursor=null,page=1,factPage=1,previous=[],factPrevious=[];
let searchExport=null,factExport=null,searchExportGeneration=0,factExportGeneration=0,snapshotError=false,snapshotBusy=false;
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=String(text);if(cls)e.className=cls;return e;};
const idValid=id=>Number.isSafeInteger(id)&&id>0;
const versionValid=v=>typeof v==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(v);
function errorText(e){const c=String(e.message).split(':')[0],key={VERSION_EXPIRED:'companyErrorExpired',INVALID_CURSOR:'companyErrorExpired',INVALID_QUERY:'companyErrorInvalid',INVALID_ID:'companyErrorInvalid',INVALID_LIMIT:'companyErrorInvalid',NOT_FOUND:'companyErrorMissing',RATE_LIMITED:'companyErrorBusy',QUERY_BUSY:'companyErrorBusy'}[c]||'companyErrorUnavailable';return t(key);}
function rows(payload){return payload?.data?.items||[];}
function mode(){const identifier=$('company-mode').value==='identifier';$('company-name-fields').hidden=identifier;$('company-name-help').hidden=identifier;$('company-identifier-fields').hidden=!identifier;$('company-identifier-help').hidden=!identifier;$('company-query').required=!identifier;$('company-namespace').required=identifier;$('company-identifier').required=identifier;}
function clearRecord(){recordGeneration++;factGeneration++;factExportGeneration++;selectedId=selectedVersion=detail=facts=factExport=null;recordError=factError=null;recordBusy=factBusy=false;factCursor=null;factPage=1;factPrevious=[];family='overview';}
function url(push=true){const u=new URL('/companies',location.origin);for(const [k,v]of new URL(location.href).searchParams)if(k.startsWith('official_'))u.searchParams.set(k,v);u.searchParams.set('lang',MhkI18n.locale);if(submitted){for(const [k,v]of Object.entries(submitted))u.searchParams.set(k,v);if(searchCursor)u.searchParams.set('cursor',searchCursor);if(page>1)u.searchParams.set('page',page);}if(selectedId){u.searchParams.set('entity',selectedId);u.searchParams.set('version',selectedVersion);u.searchParams.set('tab',family);if(factCursor)u.searchParams.set('factCursor',factCursor);if(factPage>1)u.searchParams.set('factPage',factPage);}history[push?'pushState':'replaceState']({},'',u.pathname+u.search);}
function focus(id){const e=$(id);e.focus({preventScroll:true});e.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}
function provenance(payload){if(payload)$('company-provenance-response').textContent=JSON.stringify({version:payload.meta.version,provenance:payload.provenance,warnings:payload.warnings},null,2);}
function renderSearch(){
  const items=rows(searchResult);$('company-search-status').textContent=searchError?errorText(searchError):searchBusy?t('companySearching'):searchResult?items.length?t(submitted?.q?'companyMatchCount':'companyIdentifierCount',{count:items.length}):t('companyEmpty'):t('companyInitial');
  $('company-submit').disabled=searchBusy;$('company-results-version').textContent=searchResult?`${t('companyVersion')}: ${searchResult.meta.version} · ${submitted.q||submitted.namespace+': '+submitted.value}`:'';
  $('company-results').replaceChildren();
  for(const item of items){const row=node('article',null,'company-result'),button=node('button',item.display_name||item.name1||String(item.entity_id));button.type='button';button.setAttribute('aria-pressed',String(selectedId===item.entity_id));button.addEventListener('click',()=>select(item.entity_id,searchResult.meta.version,{push:true,focus:true}));row.append(button,node('p',`${t('companyFactId')}: ${item.entity_id}${item.name_kind?' · '+item.name_kind:''}`));$('company-results').append(row);}
  $('company-next').hidden=!searchResult?.meta.nextCursor;$('company-next').disabled=searchBusy;$('company-previous').hidden=!searchCursor;$('company-previous').textContent=t(previous.length?'companyPrevious':'companyFirst');$('company-previous').disabled=searchBusy;$('company-page-number').textContent=searchResult?t('companyPageNumber',{number:page}):'';
  $('company-page-download').disabled=!items.length||searchBusy;$('company-page-receipt').textContent=searchExport?t('companyPageReady',{hash:searchExport.sha256}):'';
}
function precision(value){const labels={en:{day:'day',month:'month',year:'year',unknown:'unknown',invalid:'invalid source date',year_end:'year-end precision',month_end:'month-end precision'},zh:{day:'日',month:'月',year:'年',unknown:'未知',invalid:'來源日期無效',year_end:'年末精確度',month_end:'月末精確度'}};return labels[MhkI18n.lang][value]||value||t('companyUnknown');}
function date(raw,p){return `${raw||t('companyUnknown')} (${t('companyPrecision',{value:precision(p)})})`;}
function summary(label,value,box){box.append(node('dt',label),node('dd',value??t('companyUnknown')));}
function renderRecord(){
  $('company-record-status').textContent=recordError?errorText(recordError):recordBusy?t('companyLoadingRecord'):detail?'':t('companyNoSelection');$('company-record').hidden=!detail;
  if(!detail)return;
  const d=detail.data,zh=MhkI18n.lang==='zh';$('company-record-version').textContent=`${t('companyVersion')}: ${detail.meta.version} · Webb ID ${d.entity_id}`;
  $('company-overview').replaceChildren(node('h3',zh?(d.chinese_name||d.name1):d.name1,'company-overview-name'));
  const alternate=zh?d.name1:d.chinese_name;if(alternate)$('company-overview').append(node('p',alternate,'company-overview-other'));
  const dl=node('dl',null,'company-overview-data');summary(t('companyInc'),date(d.inc_raw,d.inc_precision),dl);summary(t('companyDissolved'),date(d.dissolved_raw,d.dissolved_precision),dl);
  for(const identifier of d.identifiers||[])summary(identifier.namespace,identifier.value,dl);$('company-overview').append(dl);
  $('company-tabs').replaceChildren();for(const [key,label]of Object.entries(families)){const b=node('button',t(label));b.type='button';b.role='tab';b.id='company-tab-'+key;b.setAttribute('aria-selected',String(family===key));b.setAttribute('aria-controls','company-facts-panel');b.tabIndex=family===key?0:-1;b.addEventListener('click',()=>changeFamily(key));b.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const keys=Object.keys(families),at=keys.indexOf(key),next=e.key==='Home'?0:e.key==='End'?keys.length-1:(at+(e.key==='ArrowRight'?1:-1)+keys.length)%keys.length;changeFamily(keys[next]);$('company-tab-'+keys[next]).focus();});$('company-tabs').append(b);}
  $('company-facts-panel').setAttribute('aria-labelledby','company-tab-'+family);renderFacts();
}
function renderFacts(){
  const payload=family==='overview'&&detail?{...detail,data:{items:[detail.data]}}:facts,items=rows(payload);$('company-facts-status').textContent=factError?errorText(factError):factBusy?t('companyFactsLoading'):payload?items.length?t('companyFactsCount',{count:items.length}):t('companyNoFacts'):'';
  $('company-facts').replaceChildren();
  if(family!=='overview')for(const item of items){const row=node('article',null,'company-fact'),party=item.party,names=partyNames(party,MhkI18n.lang);let title=item.display_name||names.primary||item.activity_label||t('companyUnknown');row.append(node('strong',title));
    if(names.secondary)row.append(node('p',names.secondary));
    if(item.role_label)row.append(node('p',`${t('companyFactRole')}: ${item.role_label}`));
    if(item.role_code!=null)row.append(node('p',`${t('companyFactRole')}: ${item.role_code===0?(MhkI18n.lang==='zh'?'代表':'Representative'):item.role_code===1?(MhkI18n.lang==='zh'?'負責人員':'Responsible officer'):item.role_code}${item.activity_label?' · '+item.activity_label:''}`));
    if(item.start_precision!=null)row.append(node('p',`${t('companyFactDates')}: ${date(item.start_raw,item.start_precision)} → ${date(item.end_raw,item.end_precision)}`));
    if(item.until_precision!=null)row.append(node('p',`${t(item.name_kind==='former_name'?'companyFormer':'companyDatePrecision')}: ${date(item.until_raw,item.until_precision)}`));
    row.append(node('small',`${t('companyFactId')}: ${item.fact_id||item.source_id}${party?' · Webb ID '+party.entityId:''}`));$('company-facts').append(row);
  }
  $('company-facts-next').hidden=family==='overview'||!facts?.meta.nextCursor;$('company-facts-next').disabled=factBusy;$('company-facts-previous').hidden=!factCursor;$('company-facts-previous').textContent=t(factPrevious.length?'companyPrevious':'companyFirst');$('company-facts-previous').disabled=factBusy;$('company-facts-page-number').textContent=family==='overview'?'':payload?t('companyPageNumber',{number:factPage}):'';
  $('company-facts-download').disabled=!items.length||factBusy||Boolean(factError);$('company-full-response').textContent=payload?JSON.stringify(payload,null,2):'';$('company-facts-receipt').textContent=factExport?t('companyPageReady',{hash:factExport.sha256}):'';
  const tools={overview:'hk_company_get',names:'hk_company_name_history',officers:'hk_company_officers',licences:'hk_company_licences',licence_relationships:'hk_company_licence_relationships'};const path='/api/v1/companies/'+selectedId+(family==='overview'?'':'/'+family),params={version:selectedVersion,...(family!=='overview'?{limit:20}:{}),...(factCursor?{cursor:factCursor}:{})};$('company-code').textContent=`GET https://mcp.hk${path}?${new URLSearchParams(params)}\n\nMCP: ${tools[family]}(${JSON.stringify({entityId:selectedId,...params})})`;
  if(payload)provenance(payload);
}
async function search({push=false,reset=true}={}){
  const generation=++searchGeneration;if(reset)clearRecord();searchExport=null;searchExportGeneration++;searchResult=null;searchError=null;searchBusy=true;if(push)url();renderSearch();renderRecord();
  const query={...submitted,limit:20,...(searchCursor?{cursor:searchCursor}:{})};
  try{const data=await api('/api/v1/companies?'+new URLSearchParams(query));if(generation!==searchGeneration)return;if(!Array.isArray(data?.data?.items)||!versionValid(data?.meta?.version))throw Error('SOURCE_SCHEMA_CHANGED');searchResult=data;provenance(data);if(!selectedId)loadSnapshot(data.meta.version);}
  catch(e){if(generation!==searchGeneration)return;searchError=e;}finally{if(generation===searchGeneration){searchBusy=false;renderSearch();}}
}
async function select(id,version,options={}){
  if(!idValid(id)||!versionValid(version)){recordError=Error('INVALID_ID');renderRecord();return;}
  clearRecord();const generation=++recordGeneration;selectedId=id;selectedVersion=version;family=Object.hasOwn(families,options.family||'')?options.family:'overview';factCursor=options.cursor||null;factPage=options.page||1;recordBusy=true;if(options.push)url();renderSearch();renderRecord();loadSnapshot(version);
  try{const data=await api(`/api/v1/companies/${id}?`+new URLSearchParams({version}));if(generation!==recordGeneration)return;if(data?.data?.kind!=='organisation'||data.data.entity_id!==id||data.meta.version!==version)throw Error('SOURCE_SCHEMA_CHANGED');detail=data;recordBusy=false;renderRecord();if(options.focus)focus('company-record-heading');if(family!=='overview')loadFacts();}
  catch(e){if(generation!==recordGeneration)return;recordBusy=false;recordError=e;renderRecord();}
}
function changeFamily(key){if(!detail)return;family=key;factCursor=null;factPage=1;factPrevious=[];factExport=null;factExportGeneration++;facts=null;factError=null;factBusy=false;factGeneration++;url();renderRecord();if(key!=='overview')loadFacts();}
async function loadFacts(){const generation=++factGeneration,id=selectedId,version=selectedVersion,key=family;facts=null;factError=null;factBusy=true;factExport=null;factExportGeneration++;renderFacts();
  try{const data=await api(`/api/v1/companies/${id}/${key}?`+new URLSearchParams({version,limit:20,...(factCursor?{cursor:factCursor}:{})}));if(generation!==factGeneration)return;if(data?.meta?.version!==version||!Array.isArray(data?.data?.items))throw Error('SOURCE_SCHEMA_CHANGED');facts=data;}
  catch(e){if(generation!==factGeneration)return;factError=e;}finally{if(generation===factGeneration){factBusy=false;renderFacts();}}
}
function renderSnapshot(){
  $('company-snapshot-status').textContent=snapshotBusy?t('companySnapshotLoading'):snapshotError||!snapshot?t('companySnapshotUnavailable'):'';$('company-snapshot-content').hidden=!snapshot;
  if(!snapshot)return;
  $('company-snapshot-version').textContent=`${t('companyVersion')}: ${snapshot.version} · ${t('companySize')}: ${(snapshot.archive.bytes/1024**2).toLocaleString(MhkI18n.locale,{maximumFractionDigits:1})} MiB`;
  for(const [id,key,filename]of [['company-snapshot-download','downloadUrl','companies-'+snapshot.version+'.tar.gz'],['company-manifest-download','manifestUrl','companies-'+snapshot.version+'-manifest.json'],['company-schema-download','schemaUrl','companies-'+snapshot.version+'-schema.json'],['company-notice-download','noticeUrl','NOTICE.txt']]){const a=$(id),u=new URL(snapshot[key],location.origin);if(u.origin!==location.origin||!u.pathname.startsWith('/downloads/companies/'))continue;a.href=u.pathname;a.download=filename;}
  $('company-snapshot-sha').textContent='SHA-256: '+snapshot.archive.sha256;$('company-snapshot-verify').textContent=`shasum -a 256 companies-${snapshot.version}.tar.gz\n\n${snapshot.archive.sha256}`;
  const labels={entities:'companyEntities',entity_identifiers:'companyIdentifiers',entity_names:'companyArchiveNames',officer_appointments:'companyOfficers',licences:'companyLicences',licence_relationships:'companyRelations',source_references:'companyReferences'};$('company-snapshot-counts').replaceChildren();for(const table of snapshot.tables)summary(t(labels[table.name]||table.name),table.rows.toLocaleString(MhkI18n.locale),$('company-snapshot-counts'));
}
async function loadSnapshot(version){if(snapshot&&snapshot.version===version){renderSnapshot();return;}const generation=++snapshotGeneration;snapshot=null;snapshotBusy=true;snapshotError=false;renderSnapshot();try{const data=await api('/downloads/companies/manifest.json'+(version?'?'+new URLSearchParams({version}):''));if(generation!==snapshotGeneration)return;if(!versionValid(data.version)||version&&data.version!==version||!Array.isArray(data.tables)||!/^[a-f0-9]{64}$/.test(data.archive?.sha256))throw Error('INVALID_MANIFEST');snapshot=data;}catch{if(generation!==snapshotGeneration)return;snapshotError=true;}finally{if(generation===snapshotGeneration){snapshotBusy=false;renderSnapshot();}}}
async function downloadPage(which){const currentGeneration=()=>which==='search'?searchExportGeneration:factExportGeneration,generation=currentGeneration(),payload=which==='search'?searchResult:family==='overview'?{...detail,data:{items:[detail.data]}}:facts,button=$(which==='search'?'company-page-download':'company-facts-download'),status=$(which==='search'?'company-page-receipt':'company-facts-receipt');if(!rows(payload).length)return;button.disabled=true;status.textContent=t('companyPreparing');try{const response=await fetch('/api/v1/companies/notice');if(!response.ok)throw Error('NOTICE_UNAVAILABLE');const notice=await response.text(),context=which==='search'?{family:'search',query:submitted,page,cursor:searchCursor}:{family,entityId:selectedId,page:factPage,cursor:factCursor};const pack=await pagePackage(payload,context,notice);if(generation!==currentGeneration())return;const link=document.createElement('a'),href=URL.createObjectURL(pack.blob);link.href=href;link.download=pack.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),60000);if(which==='search')searchExport=pack;else factExport=pack;status.textContent=t('companyPageReady',{hash:pack.sha256});}catch{if(generation===currentGeneration())status.textContent=t('companyDownloadError');}finally{if(generation===currentGeneration())button.disabled=false;}}
function restore(){searchGeneration++;clearRecord();searchResult=null;searchExport=null;searchExportGeneration++;searchError=null;searchBusy=false;previous=[];mode();const p=new URL(location.href).searchParams;submitted=p.has('namespace')?{namespace:p.get('namespace')||'',value:p.get('value')||''}:p.get('q')?{q:p.get('q')}:null;$('company-mode').value=submitted?.namespace?'identifier':'name';$('company-query').value=submitted?.q||'';$('company-namespace').value=submitted?.namespace||'webb:person';$('company-identifier').value=submitted?.value||'';mode();searchCursor=p.get('cursor');page=Math.max(1,Math.min(1000000,Number(p.get('page'))||1));renderSearch();renderRecord();if(submitted)search({reset:false});const id=Number(p.get('entity'));if(p.has('entity'))select(id,p.get('version'),{family:p.get('tab')||'overview',cursor:p.get('factCursor'),page:Math.max(1,Math.min(1000000,Number(p.get('factPage'))||1))});else loadSnapshot();}
$('company-mode').addEventListener('change',mode);
$('company-search').addEventListener('submit',e=>{e.preventDefault();submitted=$('company-mode').value==='identifier'?{namespace:$('company-namespace').value.trim(),value:$('company-identifier').value.trim()}:{q:$('company-query').value.trim()};searchCursor=null;page=1;previous=[];search({push:true});});
$('company-next').addEventListener('click',()=>{if(!searchResult?.meta.nextCursor)return;previous.push(searchCursor);searchCursor=searchResult.meta.nextCursor;page++;search({push:true});focus('company-results-heading');});
$('company-previous').addEventListener('click',()=>{searchCursor=previous.pop()||null;page=searchCursor?Math.max(1,page-1):1;search({push:true});});
$('company-facts-next').addEventListener('click',()=>{if(!facts?.meta.nextCursor)return;factPrevious.push(factCursor);factCursor=facts.meta.nextCursor;factPage++;url();loadFacts();});
$('company-facts-previous').addEventListener('click',()=>{factCursor=factPrevious.pop()||null;factPage=factCursor?Math.max(1,factPage-1):1;url();loadFacts();});
$('company-page-download').addEventListener('click',()=>downloadPage('search'));$('company-facts-download').addEventListener('click',()=>downloadPage('facts'));
window.addEventListener('popstate',restore);window.addEventListener('mhk:language',()=>{renderSearch();renderRecord();renderSnapshot();});restore();
