import {encodeRecipe} from './playground-state.js';
import {fetchPublicJson} from './http.js';
import {weatherChoices} from './source-quality.js';
/* The homepage uses the shared family copy and the real, paginated catalogue.
   Native source text is rendered verbatim as text, never as HTML. */
(() => {
  if (location.pathname !== '/') return;
  const $ = id => document.getElementById(id), t = (...args) => MhkI18n.t(...args);
  const fallback = [...$('directory-results').childNodes];
  let families = [], sequence = 0, controller;
  let state = {q:'',access:'all',provider:'all',offset:0}, nextOffset = null;
  const node = (tag,text) => {const e=document.createElement(tag);e.textContent=text;return e;};
  const localized = value => value?.[MhkI18n.locale] || value?.en || '';
  function internalLink(path,text){
    const a=node('a',text),u=new URL(path,location.origin);
    if(u.origin===location.origin){u.searchParams.set('lang',MhkI18n.locale);a.href=u.pathname+u.search+u.hash;}
    return a;
  }
  function sourceLink(path,text){const a=node('a',text);if(/^https?:\/\//i.test(path||'')){a.href=path;a.rel='noreferrer';}return a;}
  function restore(){
    const p=new URL(location.href).searchParams;
    state={q:(p.get('q')||'').slice(0,200),access:['connected','sources'].includes(p.get('access'))?p.get('access'):'all',provider:['government','independent','independent_or_public_corporation','unclassified'].includes(p.get('provider'))?p.get('provider'):'all',offset:Math.max(0,Math.min(100000,Math.trunc(Number(p.get('offset')))||0))};
    $('mhk-discovery-query').value=state.q;$('directory-access').value=state.access;$('directory-provider').value=state.provider;
  }
  function sync(){
    const u=new URL(location.href);
    for(const [key,value]of Object.entries(state)){if(value&&value!=='all')u.searchParams.set(key,value);else u.searchParams.delete(key);}
    u.searchParams.set('lang',MhkI18n.locale);history.pushState(null,'',u.pathname+u.search+u.hash);
  }
  function focusResults(){const h=$('directory-results-title');h.focus({preventScroll:true});h.scrollIntoView({block:'start',behavior:'auto'});}
  function renderRow(d){
    const connected=d.entryKind==='connected_service',family=families.find(f=>f.id===d.packId);
    const row=node('details','');row.className='mhk-directory-row';
    const summary=node('summary',''),names=node('span','');
    names.append(node('strong',MhkI18n.lang==='zh'?d.titleZhHant||d.title:d.title),node('small',[d.provider,t(d.providerType||'unclassified'),d.catalogue].filter(Boolean).join(' · ')));
    const badge=node('span',t(connected?'directoryConnected':'sourceCatalogues'));badge.className='directory-access';summary.append(names,badge);
    const detail=node('div','');detail.className='mhk-directory-detail';
    for(const choice of weatherChoices(d.id,MhkI18n.locale))detail.append(internalLink(choice.href,choice.label+' →'),document.createElement('br'));
    const description=MhkI18n.lang==='zh'?d.descriptionZhHant||d.description:d.description;
    if(description)detail.append(node('p',String(description).replace(/<[^>]*>/g,' ')));
    if(family)detail.append(node('p',localized(family.availability)),node('p',localized(family.limits)));
    detail.append(sourceLink(d.sourceUrl,d.attribution||t('originalSource')));
    detail.append(node('h3',t('directoryDates')),node('p',family?localized(family.dates):t('directorySourceDates')));
    if(d.metadataModified)detail.append(node('p',t('directoryMetadataDate')+' · '+d.metadataModified));
    if(d.referencePeriod)detail.append(node('p',t('directoryReference')+' · '+d.referencePeriod));
    if(d.updateCadence)detail.append(node('p',t('directoryCadence')+' · '+d.updateCadence));
    if(d.licence?.termsUrl)detail.append(sourceLink(d.licence.termsUrl,t('directoryTerms')));
    detail.append(node('h3',t('directoryDownloads')),node('p',family?localized(family.download):t('directoryResourceAccess')));
    if(!connected){const states=d.resourceSummary?.byStatus||{};detail.append(node('p',t('sourceCount',{total:d.resourceSummary?.total??'—'})));for(const [status,count]of Object.entries(states))detail.append(node('p',`${t(status)} · ${count}`));}
    const path='/playground'+encodeRecipe({v:1,family:connected?d.packId:'catalogue',...(connected?{}:{dataset:d.id}),lang:MhkI18n.locale});
    detail.append(internalLink(path,t('directoryOpen')+' →'));
    if(family)detail.append(document.createTextNode(' · '),internalLink(family.statusPage,t('directoryScopeLink')));
    if(connected&&d.access){detail.append(node('pre',[...(d.access.http||[]).map(p=>'GET '+p),...(d.access.tools||[]).map(tool=>'MCP: '+tool)].join('\n')));}
    detail.append(internalLink('/docs',t('apiDocs')));row.append(summary,detail);return row;
  }
  async function search({push=true,focus=false}={}){
    if(push)sync();
    const token=++sequence;controller?.abort();controller=new AbortController();
    $('directory-count').textContent=t('searching');$('directory-results').replaceChildren(node('p',t('searching')));$('directory-results').setAttribute('aria-busy','true');
    $('directory-previous').hidden=true;$('directory-next').hidden=true;nextOffset=null;
    $('directory-reset').hidden=!(state.q||state.access!=='all'||state.provider!=='all');
    document.querySelectorAll('[data-topic-query]').forEach(a=>{if(a.dataset.topicQuery===state.q)a.setAttribute('aria-current','true');else a.removeAttribute('aria-current');});
    try{
      const data=await fetchPublicJson('/api/v1/catalogue/datasets?'+new URLSearchParams({...state,order:'title',limit:10}),undefined,{signal:controller.signal});
      if(token!==sequence)return;
      $('directory-results').replaceChildren(...data.items.map(renderRow));
      $('directory-count').textContent=t('pageRange',{start:data.items.length?state.offset+1:0,end:state.offset+data.items.length,total:data.total});
      if(!data.items.length)$('directory-results').append(node('p',t('directoryEmpty')));
      nextOffset=data.nextOffset;$('directory-previous').hidden=!state.offset;$('directory-next').hidden=nextOffset==null;
    }catch(error){
      if(token!==sequence||error.name==='AbortError')return;
      $('directory-count').textContent='';const message=node('div','');message.className='mhk-directory-error';message.setAttribute('role','alert');message.append(node('p',t('directoryError')));
      const retry=node('button',t('directoryRetry'));retry.type='button';retry.className='mhk-button mhk-secondary';retry.addEventListener('click',()=>search({push:false}));message.append(retry);
      $('directory-results').replaceChildren(message,...fallback);
    }finally{if(token===sequence){$('directory-results').setAttribute('aria-busy','false');if(focus)focusResults();}}
  }
  $('mhk-discovery-form').addEventListener('submit',event=>{event.preventDefault();state.q=$('mhk-discovery-query').value.trim();state.offset=0;search({focus:true});});
  for(const field of ['provider','access'])$('directory-'+field).addEventListener('change',()=>{state[field]=$('directory-'+field).value;state.offset=0;search();});
  document.querySelectorAll('[data-topic-query]').forEach(a=>a.addEventListener('click',event=>{if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();state={q:a.dataset.topicQuery,provider:'all',access:'all',offset:0};$('mhk-discovery-query').value=state.q;$('directory-access').value='all';$('directory-provider').value='all';search({focus:true});}));
  $('directory-next').addEventListener('click',()=>{if(nextOffset!=null){state.offset=nextOffset;search({focus:true});}});
  $('directory-previous').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-10);search({focus:true});});
  $('directory-reset').addEventListener('click',()=>{state={q:'',provider:'all',access:'all',offset:0};$('mhk-discovery-query').value='';$('directory-provider').value='all';$('directory-access').value='all';search({focus:true});});
  window.addEventListener('popstate',()=>{restore();search({push:false});});
  restore();
  fetchPublicJson('/assets/datasets.json').then(data=>{families=data;}).catch(()=>{}).finally(()=>search({push:false}));
})();
