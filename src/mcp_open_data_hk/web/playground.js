import {parseExact,isNumber,exactJson} from './playground-wire.js';
import {fieldLabel} from './playground-labels.js';
import {FAMILIES,validateRecipe,encodeRecipe,decodeRecipe,RequestFlow,fieldsOf,defaultColumns,assertFields,arrivalExpiry} from './playground-state.js';
import {genericFamily,DomainSession,request,url,mcpExample} from './playground-adapters.js';
import {evidencePackage,exportPolicy} from './playground-export.js';
import {node,button,safeLink,cellText,drawChart,drawLocations} from './playground-views.js';
import {SourceHealth} from './source-health.js';
import {dateFacts,qualityText,weatherChoices} from './source-quality.js';
const $=id=>document.getElementById('pg-'+id),t=(key,values)=>MhkI18n.t('pg'+key,values),locale=()=>MhkI18n.locale;
const flow=new RequestFlow(),discoveryFlow=new RequestFlow(),detailFlow=new RequestFlow(),exportFlow=new RequestFlow();
const sourceHealth=new SourceHealth($('health'));
let families=[],draft=null,applied=null,result=null,schema=null,resource=null,session=null,pages=[],pageIndex=-1,loading=false,selectedFocus=null,expiryTimer,retryTimer,retryUntil=0,searchQuery='',choiceData={};
function emptyRecipe(family){return validateRecipe({v:1,family,lang:locale()});}
function message(text){$('status').textContent=text||'';}
function dirty(){exportFlow.cancel();$('draft').textContent=applied&&JSON.stringify(draft)!==JSON.stringify(applied)?t('Draft'):'';}
function saveUrl(replace=false){if(!applied)return;const u=new URL(location.href);u.search='?lang='+locale();u.hash=encodeRecipe({...applied,lang:locale()});const target=u.pathname+u.search+u.hash;if(target!==location.pathname+location.search+location.hash)history[replace?'replaceState':'pushState'](null,'',target);}
function controlsLoading(value){loading=value;$('output').setAttribute('aria-busy',String(value));$('apply').disabled=value||Date.now()<retryUntil;$('cancel').hidden=!value;for(const k of ['next','previous','download'])$(k).disabled=value||!result;if(value)$('download').disabled=true;}
function cancel(){flow.cancel();detailFlow.cancel();exportFlow.cancel();session?.cancel();clearInterval(retryTimer);controlsLoading(false);}
function clearResult(){result=null;pages=[];pageIndex=-1;$('output').hidden=true;$('detail').hidden=true;$('export-status').textContent='';$('share-fallback').hidden=true;clearTimeout(expiryTimer);}
function renderFamilies(){const target=$('families');target.replaceChildren();for(const family of families){const b=button(family.title[locale()],()=>openFamily(family.id));b.className='pg-family';b.dataset.family=family.id;b.setAttribute('aria-pressed',String(draft?.family===family.id));b.append(node('small',family.availability[locale()]));target.append(b);}}
function title(){const family=families.find(f=>f.id===draft?.family);$('heading').textContent=family?.title[locale()]||t('Choose');$('description').textContent=family?.question[locale()]||t('ChooseHelp');$('limits').textContent=family?.limits[locale()]||'';renderFamilies();}
function labelInput(target,label,key,value='',{type='text',options,max=200,required=false,change}={}){
  const box=node('label'),span=node('span',label),input=node(options?'select':'input');input.name=key;input.setAttribute('aria-label',label);if(options){for(const [v,text] of options){const opt=node('option',text);opt.value=v;input.append(opt);}}else{input.type=type;input.maxLength=max;}input.value=value;input.required=required;
  input.addEventListener(options?'change':'input',()=>{if(change)change(input.value);else draft.query[key]=input.value;dirty();});box.append(span,input);target.append(box);return input;
}
async function openFamily(family,recipe=null,{restore=false}={}){
  sourceHealth.show(family);
  cancel();discoveryFlow.cancel();clearResult();schema=null;resource=null;choiceData={};draft=recipe||emptyRecipe(family);applied=null;session=genericFamily(family)?null:new DomainSession(family,locale);
  $('source-choices').replaceChildren();$('selectors').replaceChildren();$('domain-controls').replaceChildren();$('filters-box').hidden=true;$('columns-box').hidden=true;$('controls').hidden=false;$('draft').textContent='';$('back').hidden=!searchQuery;title();message('');if(!restore){$('heading').focus({preventScroll:true});$('heading').scrollIntoView({block:'start'});}if(!restore)history.pushState(null,'','/playground?lang='+locale()+encodeRecipe(draft));
  if(genericFamily(family)){
    $('controls').hidden=!draft.resource;
    if(draft.resource)await inspect({saved:true,restore});
    else if(draft.dataset)await showResources(draft.dataset);
    else if(family==='transport')await discover('transport',0);
    else message(t('ChooseHelp'));
  }else{
    const run=flow.start();controlsLoading(true);
    try{choiceData=await session.choices(run.signal);if(!run.current())return;domainControls();controlsLoading(false);if(recipe&&Object.keys(recipe.query).length||family==='restaurants')await apply({restore});}
    catch(e){if(run.current()){domainControls();handleError(e);controlsLoading(false);}}
  }
}
function domainControls(){
  const box=$('domain-controls'),f=draft.family,q=draft.query;box.replaceChildren();
  const valueLabel={addresses:'Address',restaurants:'Restaurant',company_registry:'Query',enigma:'Query',hkex_daily:'Stock',webb_sdi:'Stock',sfc_archive:'CE',platehk:'Plate',seehouse:'Building'}[f];
  if(valueLabel)labelInput(box,t(valueLabel),'value',q.value||'',{required:f!=='restaurants',max:f==='platehk'?16:200});
  if(['company_registry','enigma','hkex_daily','webb_sdi','sfc_archive'].includes(f))labelInput(box,t('Source'),'source',q.source||(['enigma','webb_sdi'].includes(f)?'archive':f==='hkex_daily'?'official':'all'),{options:[['all',t('All')],['archive',t('Archive')],['official',t('Official')]],change:v=>{draft.query.source=v;delete draft.query.issuer;}});
  if(['restaurants','population'].includes(f))labelInput(box,t('District'),'district',q.district||'',{required:f==='population',options:[['',f==='population'?t('District'):t('All')],...(choiceData.districts||[]).map(d=>[d.id,d.name?.[locale()==='zh-Hant'?'zhHant':'en']||d.nameEn||d.id])]});
  if(f==='population')labelInput(box,t('Year'),'year',q.year||'',{type:'number',max:4});
  if(f==='restaurants')labelInput(box,t('LicenceType'),'licenceType',q.licenceType||'');
  if(f==='platehk'){
    labelInput(box,t('Operation'),'operation',q.operation||'search',{options:[['search',t('SearchRecords')],['comparables',t('Comparables')]]});
    labelInput(box,t('Dataset'),'dataset',q.dataset||'all',{options:['all','pvrm','tvrm_physical','tvrm_eauction','tvrm_legacy'].map(x=>[x,x==='all'?t('All'):x])});
    labelInput(box,t('SortMode'),'mode',q.mode||'exact',{options:[['exact',t('ExactMatch')],['exact_prefix',t('ExactPrefix')],['contains',t('Contains')]]});
  }
  if(f==='seehouse'){
    labelInput(box,t('Quality'),'quality',q.quality||'current',{options:[['current',t('Current')],['all',t('AllListings')]]});
    if(q.buildingId){box.append(node('p',q.buildingId));labelInput(box,t('Operation'),'operation',q.operation||'building',{options:[['building',t('Listings')],['history',t('History')]]});box.append(button(t('SearchRecords'),()=>{delete draft.query.buildingId;delete draft.query.operation;domainControls();dirty();}));}
  }
  if(f==='racing'){
    labelInput(box,t('Meeting'),'meeting',q.meeting||'',{options:[['',t('Meeting')],...(choiceData.meetings||[]).map(m=>[m.meeting.id,[m.meeting?.date,m.meeting?.venue].filter(Boolean).join(' · ')])],change:v=>{draft.query.meeting=v;delete draft.query.race;delete draft.query.profileId;}});
    labelInput(box,t('ProfileKind'),'profileKind',q.profileKind||'horse',{options:[['horse',t('Horse')],['jockey',t('Jockey')],['trainer',t('Trainer')]]});
    labelInput(box,t('ProfileId'),'profileId',q.profileId||'');
    if(q.profileId)labelInput(box,t('Operation'),'operation',q.operation||'profile',{options:[['profile',t('Details')],['history',t('History')]]});
  }
}
async function discover(query,offset=0){
  const run=discoveryFlow.start();searchQuery=query;$('discovery-results').textContent=t('Reading');
  try{const p=await request('/api/v1/catalogue/datasets',{q:query,limit:10,offset,access:draft?.family==='transport'?'sources':'all'},run.signal);if(!run.current())return;const target=$('discovery-results');target.replaceChildren();
    for(const row of p.items){const pack=row.packId||row.id?.replace(/^mcp:/,'');const b=button(locale()==='zh-Hant'?row.titleZhHant||row.title:row.title,()=>FAMILIES.includes(pack)?openFamily(pack):selectDataset(row));b.className='pg-family';b.append(node('small',[row.provider,row.catalogue,row.resourceSummary?`${row.resourceSummary.byStatus?.queryable||0} / ${row.resourceSummary.total} · ${t('Readable')}`:null].filter(Boolean).join(' · ')));target.append(b);}
    if(!p.items.length)target.append(node('p',t('Empty')));
    if(offset)target.append(button(t('Previous'),()=>discover(query,Math.max(0,offset-10))));if(p.nextOffset!=null)target.append(button(t('Next'),()=>discover(query,p.nextOffset)));
  }catch(e){if(run.current())$('discovery-results').textContent=t('Failed');}
}
async function selectDataset(row){
  await openFamily(draft?.family==='transport'?'transport':'catalogue');draft.dataset=row.id;history.pushState(null,'','/playground?lang='+locale()+encodeRecipe(draft));$('heading').textContent=locale()==='zh-Hant'?row.titleZhHant||row.title:row.title;$('description').textContent=locale()==='zh-Hant'?row.descriptionZhHant||row.description||'':row.description||'';await showResources(row.id);
}
async function showResources(dataset,offset=0){
  const run=flow.start();controlsLoading(true);message(t('Reading'));
  try{const p=await request('/api/v1/resources',{datasetId:dataset,limit:20,offset},run.signal);if(!run.current())return;const target=$('source-choices');target.replaceChildren(node('h3',t('SourcesChoice')));message(t('NoAuto'));
    for(const choice of weatherChoices(dataset,locale())){const a=node('a',choice.label+' →','mhk-button mhk-secondary');a.href=choice.href;target.append(a);}
    for(const row of p.items){
      const box=node('article',null,'pg-source-choice'),status=row.validation?.status||'pending',alias=row.aliases?.[0],name=alias?.name||row.title||row.id;
      const blocked=['restricted','unsupported'].includes(status);box.append(button(name,()=>{draft.resource=row.id;resource=row;choiceData={};draft.filters=[];draft.columns=[];draft.view={type:'table'};draft.selectors={};inspect();}));
      if(blocked)box.querySelector('button').disabled=true;
      box.append(node('p',[row.language, row.referencePeriod,alias?.inLanguage||alias?.language,row.format,MhkI18n.t(status),row.validation?.reason].filter(Boolean).join(' · ')),safeLink(row.url,t('Original')));
      if(row.validation?.freshness?.lastValidatedAt)box.append(node('p',t('Checked')+': '+MhkI18n.date(row.validation.freshness.lastValidatedAt)));
      if(blocked)box.append(node('p',t('Blocked')));else if(status!=='queryable'&&status!=='document')box.append(node('p',t('Pending')));
      target.append(box);
    }
    if(offset)target.append(button(t('Previous'),()=>showResources(dataset,Math.max(0,offset-20))));if(p.nextOffset!=null)target.append(button(t('MoreSources'),()=>showResources(dataset,p.nextOffset)));
    controlsLoading(false);
    if(p.total===1&&p.items.length===1&&p.nextOffset==null&&p.items[0].validation?.status==='queryable'&&!p.items[0].transport?.requiredParameters?.length){draft.resource=p.items[0].id;resource=p.items[0];await inspect();}
  }catch(e){if(run.current()){handleError(e);controlsLoading(false);}}
}
function selectorControls(p){
  const box=$('selectors');box.replaceChildren();const sch=p.schema||{},required=p.selectionRequired;const returned=choiceData.sourceChoices||{};for(const key of ['sheets','layers','featureTypes','parameters'])if(p[key])returned[key]=p[key];choiceData.sourceChoices=returned;
  function set(key,value){if(value==='')delete draft.selectors[key];else draft.selectors[key]=key==='layer'?Number(value):value;draft.filters=[];draft.columns=[];draft.view={type:'table'};$('filters').replaceChildren();$('filters-box').hidden=true;$('columns-box').hidden=true;schema=null;dirty();}
  const choices=[['sheet','Sheet',p.sheets||sch.availableSheets||returned.sheets||[]],['layer','Layer',p.layers||returned.layers||[]],['recordPath','RecordPath',p.featureTypes||sch.availableRecordPaths||returned.featureTypes||[]]];
  for(const [key,label,values] of choices)if(values.length){const opts=values.map(v=>typeof v==='object'?[String(v.id??v.name),v.name||String(v.id)]:[v,v]);labelInput(box,t(label),key,String(draft.selectors[key]??''),{required:required===key||key==='recordPath'&&sch.scope==='source_response_object',options:[['',t('Selection')],...opts],change:v=>set(key,v)});}
  const parameters=p.parameters||returned.parameters||resource?.transport?.requiredParameters||[];
  if(parameters.length){box.append(node('p',t('ReferenceHelp'),'mhk-note'));for(const name of parameters){const label=MhkI18n.t('param_'+name);const input=labelInput(box,label==='param_'+name?name:label,name,draft.selectors.parameters?.[name]||'',{required:true,change:v=>{draft.selectors.parameters={...draft.selectors.parameters,[name]:v};schema=null;draft.filters=[];draft.columns=[];draft.view={type:'table'};$('filters-box').hidden=true;$('columns-box').hidden=true;}});input.placeholder=p.transport?.parameterExamples?.[name]||resource?.transport?.parameterExamples?.[name]||'';}
    box.append(button(t('Reference'),()=>discover((resource?.transport?.operator||'transport')+' route stop',0)));
  }
}
async function inspect({saved=false,restore=false}={}){
  const run=flow.start();detailFlow.cancel();exportFlow.cancel();clearResult();controlsLoading(true);$('controls').hidden=false;message(t('Reading'));
  try{
    const p=await request('/api/v1/resources/'+encodeURIComponent(draft.resource)+'/schema',null,run.signal,draft.selectors);if(!run.current())return;
    if(draft.dataset&&p.resource?.datasetId!==draft.dataset)throw Error('SAVED_RESOURCE_MISSING');
    resource=p.resource;if(!resource)throw Error('SAVED_RESOURCE_MISSING');draft.dataset=resource.datasetId;if(p.dataset){$('heading').textContent=locale()==='zh-Hant'?p.dataset.titleZhHant||p.dataset.title:p.dataset.title;if(p.dataset.description)$('description').textContent=p.dataset.description;}
    $('source-choices').replaceChildren(node('p',(resource.aliases?.[0]?.name||resource.id)+' · '+resource.format),safeLink(resource.url,t('Original')));selectorControls(p);
    if(p.selectionRequired){message(t('Selection'));schema=null;controlsLoading(false);return;}
    schema=p.schema;choiceData.recordCount=p.recordCount;if(!schema)throw Error('SOURCE_SCHEMA_CHANGED');
    const paths=(schema.availableRecordPaths||[]).filter(x=>!x.includes('/0/'));
    if(!draft.selectors.recordPath&&schema.scope==='source_response_object'&&paths.length){message(t('Selection'));schema=null;controlsLoading(false);return;}
    if(saved)assertFields(draft,schema);
    if(!draft.columns.length)draft.columns=defaultColumns(schema);
    renderFilters();renderColumns();controlsLoading(false);await apply({restore,inspected:true});
  }catch(e){if(run.current()){handleError(e);controlsLoading(false);}}
}
function renderFilters(){
  const box=$('filters');box.replaceChildren();$('filters-box').hidden=!schema;
  const fields=fieldsOf(schema).filter(f=>f.types?.some(type=>!['object','array'].includes(type)));
  draft.filters.forEach((filter,index)=>{
    const row=node('div',null,'pg-filter');
    labelInput(row,t('Field'),'filter-field',filter.field,{options:fields.map(f=>[f.name,f.name]),change:value=>{filter.field=value;const kinds=fields.find(f=>f.name===value)?.scalarKinds||['string','integer','float','boolean','null'];if(!kinds.includes(filter.kind))filter.kind=kinds.find(k=>['string','integer','float','boolean','null'].includes(k))||'string';filter.value=filter.kind==='null'?'null':filter.kind==='boolean'?'true':'';renderFilters();}});
    const field=fields.find(f=>f.name===filter.field),kinds=field?.scalarKinds||['string','integer','float','boolean','null'];
    labelInput(row,t('Kind'),'filter-kind',filter.kind,{options:[...new Set([...kinds,filter.kind])].filter(k=>['string','integer','float','boolean','null'].includes(k)).map(k=>[k,t('Filter'+k[0].toUpperCase()+k.slice(1))]),change:value=>{filter.kind=value;filter.value=value==='null'?'null':value==='boolean'?'true':'';renderFilters();}});
    const input=labelInput(row,t('Value'),'filter-value',filter.value,{max:1000,change:value=>{filter.value=value;}});if(filter.kind==='null')input.readOnly=true;
    const list=node('datalist');list.id='pg-values-'+index;
    const fieldIndex=result?.presentation?.columns.indexOf(filter.field);
    if(fieldIndex>=0)for(const cell of result.presentation.rows.map(r=>r[fieldIndex]).filter(c=>c.kind===filter.kind).slice(0,20)){const opt=node('option');opt.value=cell.text;opt.label=t('PageSuggestions');list.append(opt);}input.setAttribute('list',list.id);row.append(list,button(t('Remove'),()=>{draft.filters.splice(index,1);renderFilters();dirty();}));box.append(row);
  });$('add-filter').disabled=fields.length===0||draft.filters.length>=10;
}
function renderColumns(){const box=$('columns');box.replaceChildren();$('columns-box').hidden=!schema;for(const field of fieldsOf(schema)){const label=node('label'),input=node('input');input.type='checkbox';input.value=field.name;input.checked=draft.columns.includes(field.name);input.addEventListener('change',()=>{draft.columns=input.checked?[...draft.columns,field.name]:draft.columns.filter(k=>k!==field.name);if(draft.view.type==='chart'&&[draft.view.label,draft.view.measure].some(k=>!draft.columns.includes(k)))draft.view={type:'table'};dirty();});label.append(input,node('span',field.name));box.append(label);}}
function validateDomain(q,f){
  if(['hkex_daily','webb_sdi'].includes(f)&&!/^\d{1,5}$/.test(q.value||''))throw Error('STOCK_CODE_REQUIRED');
  if(f==='sfc_archive'&&!/^[A-Za-z]{3}\d{3}$/.test(q.value||''))throw Error('CE_REFERENCE_REQUIRED');
  if(['company_registry','enigma'].includes(f)&&(q.value||'').trim().length<2)throw Error('NAME_PREFIX_REQUIRED');
  if(f==='racing'&&!q.profileId&&!q.meeting)throw Error('MEETING_REQUIRED');
}
async function apply({restore=false,inspected=false,next=false,retry=false,refresh=false}={}){
  if(!draft||Date.now()<retryUntil)return;
  if(genericFamily(draft.family)&&!schema&&!inspected&&!next&&!retry){await inspect();return;}
  const run=flow.start();detailFlow.cancel();exportFlow.cancel();$('detail').hidden=true;$('export-status').textContent='';$('recovery').replaceChildren();controlsLoading(true);message(t('Reading'));
  const old=result;
  try{
    const recipe=validateRecipe(next||retry?applied:draft);encodeRecipe(recipe);if(!genericFamily(recipe.family))validateDomain(recipe.query,recipe.family);
    let out;
    if(genericFamily(recipe.family)){
      if(!recipe.columns.length&&choiceData.recordCount!==0)throw Error('CHOOSE_COLUMNS');assertFields(recipe,next||retry?old?.envelopes[0]?.schema:schema);
      const continuation=next?old?.next:0;
      const body={...recipe.selectors,typedFilters:recipe.filters,fields:recipe.columns,limit:20,offset:continuation||0,presentation:true,...(!refresh&&old?.version?{version:old.version}:{})};
      const p=await request('/api/v1/resources/'+encodeURIComponent(recipe.resource)+'/query',null,run.signal,body);if(!run.current())return;
      if(!p.presentation||p.presentation.rows.length!==p.data.items.length)throw Error('EXACT_RESPONSE_REQUIRED');
      out={rows:p.data.items,presentation:p.presentation,envelopes:[p],total:p.meta.total,next:p.meta.nextOffset,version:p.meta.version,errors:[]};
    }else out=await session.read(recipe,run.signal,{next,retry});
    if(!run.current())return;
    result=out;applied=recipe;
    if(!next&&!retry){pages=[];pageIndex=-1;}else pages=pages.slice(0,pageIndex+1);
    if(retry&&pageIndex>=0)pages[pageIndex]=out;else pages.push(out);if(pages.length>3)pages.shift();pageIndex=pages.length-1;
    if(!restore)saveUrl();dirty();renderResult();
  }catch(e){if(run.current()){if(old){result=old;renderResult();message(t('ScopePrevious'));}handleError(e);}}
  finally{if(run.current()){controlsLoading(false);if(result)renderButtons();}}
}
function handleError(e){
  if(e.name==='AbortError')return;
  $('recovery').replaceChildren();let copy=/RECIPE/.test(e.message)?t('InvalidRecipe'):/VERSION_CHANGED/.test(e.message)?t('VersionChanged'):/SAVED_|UNKNOWN_FIELD/.test(e.message)?t('SavedMissing'):t('Failed');message(copy);
  const details=node('details');details.append(node('summary',MhkI18n.t('technicalDetails')),node('pre',e.message));$('recovery').append(details);
  $('recovery').append(button(/VERSION_CHANGED/.test(e.message)?t('Restart'):t('Refresh'),()=>apply({refresh:true})));
  if(e.retryAfter){retryUntil=Date.now()+Math.min(300,e.retryAfter)*1000;clearInterval(retryTimer);const tick=()=>{const n=Math.max(0,Math.ceil((retryUntil-Date.now())/1000));message(n?t('Busy',{n}):copy);$('apply').disabled=n>0;if(!n)clearInterval(retryTimer);};tick();retryTimer=setInterval(tick,1000);}
}
function renderButtons(){
  $('previous').disabled=loading||pageIndex<1;
  $('next').disabled=loading||!result?.next||result?.expired;
  $('download').disabled=loading||!exportPolicy(result,applied);
  $('download').textContent=t('Download',{n:result?.rows.length||0});
  $('export-policy').textContent=exportPolicy(result,applied)?t('Exact'):t('ExportDisabled');
}
function renderResult(){
  if(!result)return;clearTimeout(expiryTimer);$('output').hidden=false;$('table').replaceChildren();$('provenance').replaceChildren();$('source-export').replaceChildren();$('dates').replaceChildren();$('warnings').replaceChildren();$('code').textContent='';$('table').scrollLeft=0;$('table').scrollTop=0;
  const p=result.presentation,table=node('table'),head=node('thead'),tr=node('tr');table.append(node('caption',t('Scope')));
  const first=node('th',t('Details'));first.scope='col';tr.append(first);for(const name of p.columns){const th=node('th',fieldLabel(name,locale()));th.title=name;th.scope='col';tr.append(th);}head.append(tr);table.append(head);const body=node('tbody');
  p.rows.forEach((cells,i)=>{const row=node('tr'),detail=node('td'),action=result.actions?.[i];const detailButton=button(action?.kind==='issuer'?t('Issuer'):action?.kind==='building'?t('Building'):action?.kind==='race'?t('Race'):t('Details'),()=>openRow(i));detailButton.setAttribute('aria-label',t('Details')+' · '+(i+1)+' · '+cells.map(c=>cellText(c,locale())).filter(c=>c&&c!=='…').slice(0,2).join(' · '));detail.append(detailButton);row.append(detail);cells.forEach((cell,i)=>{const td=node('td',cellText(cell,locale(),p.columns[i]==='dtstart'&&result.envelopes[0]?.schema?.scope==='calendar_events'));if(cell.kind==='json')td.title=t('Details');row.append(td);});body.append(row);});table.append(body);$('table').append(table);
  $('count').textContent=t('Records',{n:result.rows.length});$('scope').textContent=(result.total==null?t('Unknown'):t('Total',{n:result.total}))+' · '+t('Scope');
  message(result.errors?.length?t(result.rows.length?'Partial':'Failed'):!result.rows.length?t('Empty'):'');$('recovery').replaceChildren();if(result.errors?.length){for(const e of result.errors)$('recovery').append(node('p',e.source+' · '+e.message));$('recovery').append(button(t('Retry'),()=>apply({retry:true})));}
  for(const envelope of result.envelopes){
    const qualified=qualityText(envelope,locale());if(qualified)$('warnings').append(node('p',qualified));
    for(const [label,value]of dateFacts(envelope).filter(([label])=>['Observed','Retrieved','Checked','ReferencePeriod'].includes(label)))$('dates').append(node('p',t(label)+': '+(['Observed','Retrieved','Checked'].includes(label)?MhkI18n.date(value):value)));
    const dl=node('dl',null,'pg-source-facts');
    for(const [label,value]of [...dateFacts(envelope),['Version',envelope.meta?.version]])if(value!=null)dl.append(node('dt',t(label)),node('dd',typeof value==='object'?JSON.stringify(value):String(value)));
    for(const source of envelope.provenance||[])if(source.sourceUrl||source.url)dl.append(node('dt',t('Original')),safeLink(source.sourceUrl||source.url,t('Original')));
    $('provenance').append(dl);
    for(const warning of envelope.warnings||[])$('warnings').append(node('p',warning.message||warning.code));
    if(envelope.data?.method)$('warnings').append(node('p',envelope.data.method));
    const coverage=envelope.coverage||envelope.data?.releaseScope||envelope.data?.listingQuality;if(coverage){const box=node('details');box.append(node('summary',MhkI18n.t('coverageDetail')),node('pre',JSON.stringify(coverage,null,2)));$('warnings').append(box);}
    const full=node('details');full.append(node('summary',t('Contract')),node('pre',envelope.wire||JSON.stringify(envelope,null,2)));$('provenance').append(full);
    if(envelope.request){const req=envelope.request;const code=req.body?'POST '+req.path+'\n'+JSON.stringify(req.body,null,2):'GET '+req.path;$('code').textContent+=code+'\n\n'+(mcpExample(req)?'MCP: '+mcpExample(req)+'\n\n':'');}
    const expiry=arrivalExpiry(envelope);
    if(expiry!==null){
      if(expiry<=Date.now()){result.expired=true;exportFlow.cancel();detailFlow.cancel();$('detail').hidden=true;$('detail-content').replaceChildren();message(t('Expired'));$('table').replaceChildren(node('p',t('Expired')));}
      else expiryTimer=setTimeout(()=>{result.expired=true;exportFlow.cancel();detailFlow.cancel();$('detail').hidden=true;$('detail-content').replaceChildren();$('table').replaceChildren(node('p',t('Expired')));$('plot').replaceChildren();$('map').replaceChildren();message(t('Expired'));renderButtons();$('recovery').replaceChildren(button(t('Refresh'),()=>apply({refresh:true})));},expiry-Date.now()+1);
    }
    if(envelope.schema?.scope==='document_pages')$('provenance').prepend(node('p',t('Document')));
  }
  if(applied.resource)$('code').textContent+='MCP: hk_resource_query('+JSON.stringify({resourceId:applied.resource,...result.envelopes[0].request?.body},null,2)+')';
  if(result.exportUrl){const a=node('a',t(result.exportKind==='profile'?'DownloadProfile':'DownloadRace'),'mhk-button mhk-secondary');a.href=result.exportUrl;a.download='racing-results.zip';$('source-export').append(a,node('p',t(result.exportKind==='profile'?'DownloadProfileScope':'DownloadRaceScope'),'mhk-note'));}
  chartControls();
  $('plot').replaceChildren();if(!result.expired&&applied.view?.type==='chart')try{drawChart($('plot'),p,applied.view,t);}catch{message(t('ChartInvalid'));}
  if(['addresses','restaurants'].includes(applied.family)&&!result.expired)drawLocations($('map'),result.rows,t);else $('map').replaceChildren();
  $('chart').hidden=applied.view?.type!=='chart';$('chart-tab').setAttribute('aria-pressed',String(!$('chart').hidden));$('table-tab').setAttribute('aria-pressed',String($('chart').hidden));renderButtons();
}
function chartControls(){for(const k of ['chart-label','chart-measure']){$(k).replaceChildren();for(const name of result.presentation.columns){const opt=node('option',fieldLabel(name,locale()));opt.value=name;$(k).append(opt);}}const view=applied.view?.type==='chart'?applied.view:result.chart;if(view){$('chart-label').value=view.label;$('chart-measure').value=view.measure;$('chart-unit').value=view.unit||'';}else $('chart-unit').value='';}
function closeDetail(){detailFlow.cancel();$('detail').hidden=true;selectedFocus?.focus({preventScroll:true});}
async function openRow(index){
  if(result?.expired)return;selectedFocus=document.activeElement;const action=result.actions?.[index];
  if(action?.kind==='issuer'){draft.query.issuer=action.item.id;await apply();return;}
  if(action?.kind==='building'){draft.query.buildingId=action.id;draft.query.operation='building';domainControls();await apply();return;}
  if(action?.kind==='race'){draft.query.race=action.id;await apply();return;}
  const run=detailFlow.start();$('detail').hidden=false;$('detail-content').replaceChildren(node('p',t('Reading')));$('detail-heading').focus({preventScroll:true});$('detail').scrollIntoView({block:'start'});
  const body=$('detail-content');
  try{
    if(action){const detail=await session.detail(action,run.signal);if(!run.current())return;body.replaceChildren();for(const p of detail.envelopes){const d=p.wire?parseExact(p.wire).data:p.data;renderFacts(body,d);const original=node('details');original.append(node('summary',t('Contract')),node('pre',p.wire||JSON.stringify(p,null,2)));body.append(original);if(p.licences)showHistoryRows(body,p.licences);}
      if(detail.history)historyControls(detail.history,body);
    }else{const p=result.presentation,cells=p.rows[index];body.replaceChildren();const dl=node('dl',null,'pg-source-facts');cells.forEach((cell,i)=>dl.append(node('dt',fieldLabel(p.columns[i],locale())),node('dd',cell.kind==='missing'?'— (missing)':cell.kind==='string'?cell.text:cell.json)));body.append(dl);}
  }catch(e){if(run.current())body.replaceChildren(node('p',t('Failed')),node('pre',e.message));}
}
function renderFacts(target,data,depth=0){
  if(!data||typeof data!=='object')return;
  const dl=node('dl',null,'pg-source-facts');
  const groups=new Set(['name','address','identity','latestAddress','identifier','observations','activities','interests','revision','revision_links','appearances','dividends','statistics','before','after','events','attributes','sourceCutoff','quality','freshness','match','listingState']);
  for(const [key,value] of Object.entries(data)){
    if(value==null||typeof value!=='object'||isNumber(value))dl.append(node('dt',fieldLabel(key,locale())),node('dd',isNumber(value)?value.text:value==null?t('Unknown'):String(value)));
    else if(depth<2&&groups.has(key)){const group=node('section');group.append(node('h4',fieldLabel(key,locale())));for(const item of (Array.isArray(value)?value.slice(0,20):[value]))renderFacts(group,item,depth+1);target.append(group);}
  }
  target.prepend(dl);
}
function showHistoryRows(target,p){
  const data=p.wire?parseExact(p.wire).data:p.data;const rows=Array.isArray(data)?data:data?.items||[];
  if(!rows.length)target.append(node('p',t('Empty')));
  for(const item of rows){const article=node('article',null,'pg-history-record');renderFacts(article,item);const original=node('details');original.append(node('summary',t('Contract')),node('pre',exactJson(item)));article.append(original);target.append(article);}

}
function historyControls(context,target){
  const nav=node('div',null,'mhk-actions'),list=node('div'),more=button(t('HistoryMore'),()=>load(true));let family=context.families[0],cursor=null;more.hidden=true;
  for(const key of context.families){const copy={names:'Names',officers:'Officers',licences:'Licences',addresses:'Addresses',licence_relationships:'LicenceRelationships',history:'History'}[key];nav.append(button(t(copy),()=>{family=key;cursor=null;load();}));}target.append(node('h3',t('History')),nav,list,more);
  async function load(next=false){const run=detailFlow.start();more.disabled=true;list.replaceChildren(node('p',t('Reading')));try{const p=await session.history(context,family,next?cursor:null,run.signal);if(!run.current())return;const rows=Array.isArray(p.data)?p.data:p.data?.items;if(p.meta?.version!==context.version||!Array.isArray(rows))throw Error('SOURCE_IDENTITY_CHANGED');list.replaceChildren();showHistoryRows(list,p);cursor=p.meta?.nextCursor;more.hidden=!cursor;}catch(e){if(run.current())list.replaceChildren(node('p',t('Failed')),node('pre',e.message));}finally{if(run.current())more.disabled=false;}}
}
async function restore(){let recipe;try{recipe=decodeRecipe(location.hash);}catch{cancel();clearResult();message(t('InvalidRecipe'));return;}if(recipe){recipe.lang=locale();await openFamily(recipe.family,recipe,{restore:true});}else{sourceHealth.clear();cancel();clearResult();draft=null;applied=null;$('controls').hidden=true;title();message(t('ChooseHelp'));}}
$('search').addEventListener('submit',e=>{e.preventDefault();discover($('topic').value.trim(),0);});
$('controls').addEventListener('submit',e=>{e.preventDefault();apply();});
$('add-filter').addEventListener('click',()=>{const field=fieldsOf(schema).find(f=>!draft.filters.some(p=>p.field===f.name)&&f.types.some(t=>!['object','array'].includes(t)));if(!field)return;const kind=(field.scalarKinds||[]).find(k=>['string','integer','float','boolean','null'].includes(k))||'string';draft.filters.push({field:field.name,kind,value:kind==='null'?'null':kind==='boolean'?'true':''});renderFilters();dirty();});
$('reset').addEventListener('click',()=>{if(!draft)return;draft.filters=[];draft.columns=schema?defaultColumns(schema):[];draft.view={type:'table'};if(schema){renderFilters();renderColumns();}dirty();apply({refresh:true});});
$('cancel').addEventListener('click',()=>{cancel();message('');if(result)renderButtons();});
$('back').addEventListener('click',()=>{$('topic').focus();$('discovery-results').scrollIntoView({block:'start'});});
$('next').addEventListener('click',()=>apply({next:true}));
$('previous').addEventListener('click',()=>{if(pageIndex<1)return;cancel();pageIndex--;result=pages[pageIndex];if(session?.feed&&session.feed.index>0)session.previous();if(session)session.current=result;renderResult();});
$('table-tab').addEventListener('click',()=>{if(!applied)return;applied.view={type:'table'};draft.view={type:'table'};saveUrl();$('chart').hidden=true;$('table-tab').setAttribute('aria-pressed','true');$('chart-tab').setAttribute('aria-pressed','false');dirty();});
$('chart-tab').addEventListener('click',()=>{$('chart').hidden=false;$('chart-tab').setAttribute('aria-pressed','true');$('table-tab').setAttribute('aria-pressed','false');});
$('chart-form').addEventListener('submit',e=>{e.preventDefault();if(result?.expired){message(t('Expired'));return;}try{const view={type:'chart',label:$('chart-label').value,measure:$('chart-measure').value,unit:$('chart-unit').value};drawChart($('plot'),result.presentation,view,t);applied.view=view;draft.view=structuredClone(view);saveUrl();dirty();}catch{message(t('ChartInvalid'));}});
$('detail-close').addEventListener('click',closeDetail);$('detail').addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail();});
$('share').addEventListener('click',async()=>{if(!applied)return;const share=new URL(location.pathname,location.origin);share.searchParams.set('lang',locale());share.hash=encodeRecipe({...applied,lang:locale()});try{await navigator.clipboard.writeText(share.href);$('export-status').textContent=t('Copied');}catch{$('share-fallback').hidden=false;$('share-fallback').querySelector('input').value=share.href;$('share-fallback').querySelector('input').select();}});
$('download').addEventListener('click',async()=>{if(!exportPolicy(result,applied))return;const run=exportFlow.start(),captured=structuredClone(result),recipe=structuredClone(applied);$('download').disabled=true;try{const pack=await evidencePackage(captured,recipe,run.signal);if(!run.current())return;const a=node('a'),href=URL.createObjectURL(pack.blob);a.href=href;a.download=pack.filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(href),5000);$('export-status').textContent=t('Downloaded',{hash:pack.sha256});}catch(e){if(run.current())$('export-status').textContent=t('Failed')+' '+e.message;}finally{if(run.current())renderButtons();}});
window.addEventListener('hashchange',()=>{if(!applied||location.hash!==encodeRecipe({...applied,lang:locale()}))restore();});
window.addEventListener('mhk:language',()=>{sourceHealth.render();title();if(session)domainControls();if(result)renderResult();});
try{families=await fetch('/assets/datasets.json').then(r=>{if(!r.ok)throw Error('DIRECTORY_UNAVAILABLE');return r.json();});renderFamilies();await restore();}catch{message(t('Failed'));}
