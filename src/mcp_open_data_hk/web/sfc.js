/* Existing attributed Webb facts only. No official-source collection is invoked. */
import {fetchPublicJson} from './http.js';
const form=document.querySelector('#sfc-archive-search');
const status=document.querySelector('#sfc-archive-status');
const results=document.querySelector('#sfc-archive-results');
const record=document.querySelector('#sfc-archive-record');
let generation=0,controller;
const t=key=>window.MhkI18n.t(key);
function element(tag,text){const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;}
function date(raw,precision){return raw==null||raw===''?t('sfcArchiveUnknown'):String(raw)+' · '+String(precision||'unknown');}
async function select(row,version,run,signal){
 const query=new URLSearchParams({version,limit:'20'});
 const response=await fetchPublicJson('/api/v1/companies/'+row.entity_id+'/licences?'+query,null,{signal});
 if(run!==generation)return;
 if(response.meta?.version!==version||!Array.isArray(response.data?.items)||response.data.items.length>20)throw new Error('SOURCE_SCHEMA_CHANGED');
 const rows=response.data.items;
 if(rows.some(r=>r.company_id!==row.entity_id))throw new Error('SOURCE_IDENTITY_CHANGED');
 const content=element('section');content.append(element('h3',row.name1||row.matched_names?.[0]?.display_name||String(row.entity_id)),element('p',t('sfcArchiveDated')+' '+version));
 if(!rows.length)content.append(element('p',t('sfcArchiveEmptyFacts')));
 else {
  const scroll=element('div');scroll.className='company-table-wrap';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',t('sfcArchiveIntervals'));
  const table=element('table'),head=element('thead'),header=element('tr');
  for(const key of ['sfcArchiveType','sfcArchiveActivity','sfcArchiveStart','sfcArchiveEnd']){const th=element('th',t(key));th.scope='col';header.append(th);}head.append(header);table.append(head);
  const body=element('tbody');for(const row of rows){const tr=element('tr');tr.append(element('td',row.registered_institution===0?t('sfcArchiveCorporation'):row.registered_institution===1?t('sfcArchiveInstitution'):t('sfcArchiveUnknown')),element('td',row.activity_label||String(row.activity_id)),element('td',date(row.start_raw,row.start_precision)),element('td',date(row.end_raw,row.end_precision)));body.append(tr);}table.append(body);scroll.append(table);content.append(scroll);
 }

 if(response.meta.nextCursor)content.append(element('p',t('sfcArchivePartial')));
 const link=element('a',t('sfcArchiveMore'));link.href='/companies?'+new URLSearchParams({companySource:'archive',entity:String(row.entity_id),version,tab:'licences',lang:window.MhkI18n.locale});content.append(link);
 record.replaceChildren(content);record.hidden=false;status.textContent=t('sfcArchiveLoaded');
}
form?.addEventListener('submit',async event=>{
 event.preventDefault();const input=document.querySelector('#sfc-archive-ce');const ce=input.value.toUpperCase();
 if(!/^[A-Z]{3}[0-9]{3}$/.test(ce)){input.setCustomValidity(t('sfcArchiveInvalid'));input.reportValidity();return;}input.setCustomValidity('');
 const run=++generation;controller?.abort();controller=new AbortController();const {signal}=controller;status.textContent=t('sfcArchiveLoading');
 try{
  const query=new URLSearchParams({namespace:'sfc:ce_reference',value:ce,groupBy:'organisation',limit:'20'});
  const response=await fetchPublicJson('/api/v1/companies?'+query,null,{signal});if(run!==generation)return;
  const rows=response.data?.items,version=response.meta?.version;
  if(!Array.isArray(rows)||typeof version!=='string'||!/^[A-Za-z0-9._-]{1,100}$/.test(version)||rows.length>20||rows.some(r=>!Number.isSafeInteger(r.entity_id)||r.entity_id<1))throw new Error('SOURCE_SCHEMA_CHANGED');
  results.replaceChildren();
  if(!rows.length){record.hidden=true;record.replaceChildren();status.textContent=t('sfcArchiveNoMatch');return;}
  if(rows.length===1){await select(rows[0],version,run,signal);return;}
  record.hidden=true;status.textContent=t('sfcArchiveChoose');
  for(const row of rows){const button=element('button',row.name1||row.matched_names?.[0]?.display_name||String(row.entity_id));button.type='button';button.className='mhk-button mhk-secondary';button.addEventListener('click',()=>select(row,version,run,signal).catch(()=>{if(run===generation)status.textContent=t('sfcArchiveFailed');}));results.append(button);}
 }catch(error){if(error.name!=='AbortError'&&run===generation)status.textContent=t('sfcArchiveFailed');}
});
document.querySelector('#sfc-archive-ce')?.addEventListener('input',event=>event.target.setCustomValidity(''));
window.addEventListener('mhk:language',()=>{generation++;controller?.abort();results.replaceChildren();record.hidden=true;status.textContent='';});

// These reads use accepted private-reader facts; browser actions never collect.
const liveForm=document.querySelector('#sfc-live-search');
const liveInput=document.querySelector('#sfc-ce');
const liveButton=document.querySelector('#sfc-live-verify');
const liveStatus=document.querySelector('#sfc-live-status');
const liveRecord=document.querySelector('#sfc-live-record');
let liveGeneration=0,liveController,liveCapability;
async function capability(){
 const run=++liveGeneration;liveController?.abort();liveController=new AbortController();liveInput.disabled=true;liveButton.disabled=true;
 try{
  const response=await fetchPublicJson('/api/v1/sfc/status',null,{signal:liveController.signal});
  if(run!==liveGeneration)return;
  liveCapability=response.data;
  const ready=Array.isArray(liveCapability?.enabledModes)&&['rest','browser'].every(m=>liveCapability.enabledModes.includes(m))&&/^sfc-[a-f0-9]{32}$/.test(liveCapability.acceptedVersion||'');
  liveInput.disabled=!ready;liveButton.disabled=!ready;liveButton.textContent=t(ready?'sfcLiveVerify':'sfcVerify');
  liveStatus.textContent=t(ready?'sfcLiveReady':'sfcLiveUnavailable');
  if(ready){document.querySelector('#sfc-ce-heading').textContent=t('sfcLiveReady');document.querySelector('#sfc-hint').textContent=t('sfcLiveScope');document.querySelector('label[for="sfc-ce"]').textContent=t('sfcArchiveCe');document.querySelector('[data-i18n="sfcModes"]').textContent=t('sfcLiveScope');const q=new URLSearchParams(location.search);if(q.get('view')==='sfc_observation'&&/^[A-Z]{3}[0-9]{3}$/.test(q.get('ce')||'')){liveInput.value=q.get('ce');liveForm.requestSubmit();}}
 }catch(error){if(error.name!=='AbortError'&&run===liveGeneration){liveInput.disabled=true;liveButton.disabled=true;liveStatus.textContent=t('sfcLiveUnavailable');}}
}
liveForm?.addEventListener('submit',async event=>{
 event.preventDefault();if(liveInput.disabled)return;
 const ce=liveInput.value.toUpperCase();
 if(!/^[A-Z]{3}[0-9]{3}$/.test(ce)){liveInput.setCustomValidity(t('sfcArchiveInvalid'));liveInput.reportValidity();return;}liveInput.setCustomValidity('');
 const run=++liveGeneration;liveController?.abort();liveController=new AbortController();liveStatus.textContent=t('sfcArchiveLoading');
 try{
  const currentQuery=new URLSearchParams(location.search);const version=currentQuery.get('ce')===ce&&/^sfc-[a-f0-9]{32}$/.test(currentQuery.get('version')||'')?currentQuery.get('version'):liveCapability.acceptedVersion;
  const response=await fetchPublicJson('/api/v1/sfc/corporations/'+ce+'?'+new URLSearchParams({version}),null,{signal:liveController.signal});
  if(run!==liveGeneration)return;
  const fact=response.data;
  if(response.meta?.version!==version||fact?.ce!==ce||!Array.isArray(fact.activities)||fact.activities.length>50)throw new Error('SOURCE_SCHEMA_CHANGED');
  const shared=new URL(location.href);shared.searchParams.set('view','sfc_observation');shared.searchParams.set('ce',ce);shared.searchParams.set('version',version);history.replaceState(null,'',shared);
  const section=element('section');section.append(element('h3',fact.nameEn||fact.nameZhHant||ce),element('p',ce+' · '+(fact.statusLabel||t('sfcArchiveUnknown'))),element('p',t('sfcLiveScope')),element('p',t('sfcLiveObserved')+': '+fact.observedAt+' · '+version),element('p',t('sfcLiveSourceCutoff')+': '+date(fact.sourceCutoff?.raw,fact.sourceCutoff?.precision)));
  const scroll=element('div');scroll.className='company-table-wrap';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',t('sfcArchiveIntervals'));
  const table=element('table'),thead=element('thead'),head=element('tr');
  for(const key of ['sfcArchiveActivity','sfcArchiveStart','sfcArchiveEnd']){const th=element('th',t(key));th.scope='col';head.append(th);}thead.append(head);table.append(thead);
  const tbody=element('tbody');for(const row of fact.activities){const tr=element('tr');tr.append(element('td',row.label+' · '+row.statusLabel),element('td',date(row.start?.raw,row.start?.precision)),element('td',date(row.end?.raw,row.end?.precision)));tbody.append(tr);}table.append(tbody);scroll.append(table);section.append(scroll);
  if(liveCapability.historyAvailable===true){
   const button=element('button',t('sfcObservationHistory')),items=element('ul');button.type='button';button.className='mhk-button mhk-secondary';button.id='sfc-observation-history';let cursor=null;
   button.addEventListener('click',async()=>{button.disabled=true;try{
    const query=new URLSearchParams({version,limit:'20'});if(cursor)query.set('cursor',cursor);
    const page=await fetchPublicJson('/api/v1/sfc/corporations/'+ce+'/history?'+query,null,{signal:liveController.signal});if(run!==liveGeneration)return;
    if(page.meta?.version!==version||!Array.isArray(page.data)||page.data.length>20||page.data.some(row=>row.ce!==ce||!/^sfc-[a-f0-9]{32}$/.test(row.version)))throw new Error('SOURCE_SCHEMA_CHANGED');
    for(const row of page.data){const li=element('li'),link=element('a',row.observedAt+' · '+row.version);link.href='/sfc?'+new URLSearchParams({view:'sfc_observation',ce,version:row.version,lang:window.MhkI18n.locale});li.append(link);items.append(li);}
    cursor=page.meta.nextCursor||null;button.hidden=!cursor;button.textContent=t('sfcHistoryMore');button.disabled=false;liveStatus.textContent=t('sfcHistoryScope');
   }catch(error){if(error.name!=='AbortError'&&run===liveGeneration){button.disabled=false;liveStatus.textContent=t('sfcLiveFailed');}}});
   section.append(element('p',t('sfcHistoryScope')),button,items);
  }
  if(response.meta?.export&&response.meta.export.url==='/api/v1/sfc/exports/'+version+'.zip'){const download=element('a',t('sfcExportDownload'));download.id='sfc-observation-download';download.className='mhk-button mhk-secondary';download.href=response.meta.export.url;download.download=version+'.zip';section.append(element('p',t('sfcExportScope')),download);}
  liveRecord.replaceChildren(section);liveRecord.hidden=false;liveRecord.focus();liveStatus.textContent=t('sfcLiveLoaded');
 }catch(error){if(error.name!=='AbortError'&&run===liveGeneration)liveStatus.textContent=t('sfcLiveFailed');}
});
liveInput?.addEventListener('input',()=>liveInput.setCustomValidity(''));
window.addEventListener('mhk:language',()=>{liveRecord.hidden=true;liveRecord.replaceChildren();capability();});
if(liveForm)capability();
