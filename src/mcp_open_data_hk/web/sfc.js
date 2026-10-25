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

 const link=element('a',t('sfcArchiveMore'));link.href='/companies?companySource=archive&entity='+row.entity_id+'&version='+encodeURIComponent(version);content.append(link);
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
