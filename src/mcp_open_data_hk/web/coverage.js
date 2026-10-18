import {fetchPublicJson} from './http.js';
/* Source data is always rendered as text and retains its original language. */
(() => {
  const $ = id => document.getElementById(id), t = (...args) => MhkI18n.t(...args);
  let searchSequence = 0, resourceSequence = 0, requestGeneration = 0;
  let selected = null, nextRecords = null, lastQuery = null, searchOffset = 0, resourceOffset = 0;
  let datasetId = null, datasetTitle = '', access = 'connected', submittedQuery = '', directoryMode = false, busy = false;
  let inventory = null, inventoryFailed = false, datasets = null, resourceList = null, result = null;
  let searchError = null, resourceError = null, queryError = null, expiryTimer = null;
  const api = fetchPublicJson;
  const node = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
  function link(url, title) { const a = node('a', title); if (/^https?:\/\//i.test(url)) { a.href = url; a.rel = 'noreferrer'; } return a; }
  function failure(error) { const code=error.message.split(':')[0];const known={SOURCE_NOT_FOUND:'sourceUnavailablePlain',ACCESS_RESTRICTED:'sourceDeniedPlain',STALE_TRANSPORT_DATA:'sourceStalePlain',PARAMETERS_REQUIRED:'sourceSettingsPlain'}[code];if(known)return t(known);return MhkI18n.lang === 'en' ? error.message : `${t(error instanceof SyntaxError ? 'invalidJson' : 'sourceError')} (${error.message.split(':')[0].slice(0,80)})`; }
  function renderCoverage() {
    MhkI18n.coverageSummary($('coverage-summary'), inventory, inventoryFailed);
    if (inventory) $('coverage-detail').textContent = JSON.stringify(inventory, null, 2);
  }
  async function coverage() {
    try { inventory = await api('/api/v1/coverage'); inventoryFailed = false; } catch { inventoryFailed = true; }
    renderCoverage();
  }
  function title(d) { return MhkI18n.lang === 'zh' ? d.titleZhHant || d.title || d.id : d.title || d.id; }
  function internalLink(url, text) { const a=node('a',text), u=new URL(url,location.origin); if(u.origin===location.origin){u.searchParams.set('lang',MhkI18n.locale);a.href=u.pathname+u.search+u.hash;}return a; }
  function focusSection(id) { const e=$(id);e.focus({preventScroll:true});e.scrollIntoView({behavior:window.matchMedia?.('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'}); }
  function syncUrl(push=true) {
    const u=new URL(location.href);u.searchParams.set('q',submittedQuery);u.searchParams.set('access',access);u.searchParams.set('lang',MhkI18n.locale);
    for(const [key,value] of [['dataset',datasetId],['resource',selected?.id],['offset',searchOffset||null],['sourceOffset',resourceOffset||null],['format',$('resource-format').value||null]]) {if(value!=null)u.searchParams.set(key,value);else u.searchParams.delete(key);}
    history[push?'pushState':'replaceState'](null,'',u.pathname+u.search+u.hash);
  }
  function resetPreview() {
    ++requestGeneration; selected=null;result=null;queryError=null;lastQuery=null;nextRecords=null;busy=false;
    $('record-query').reset();$('source-inputs').replaceChildren();$('record-path-choices').replaceChildren();$('record-response').textContent='';$('resource-code').textContent=t('selectForCode');$('preview-step').hidden=true;renderSelection();renderQuery();
  }
  function resetDataset() { ++resourceSequence;datasetId=null;datasetTitle='';resourceList=null;resourceError=null;directoryMode=false;resourceOffset=0;$('resource-format').value='';clearTimeout(expiryTimer);$('resource-step').hidden=true;resetPreview();renderResources(); }
  function renderDatasets() {
    $('datasets').replaceChildren();
    document.querySelectorAll('[data-access]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.access===access)));
    if (!datasets) { $('datasets').textContent = searchError ? failure(searchError) : t('searching'); return; }
    $('dataset-total').textContent = t('datasetMatches', {total: datasets.total, shown: datasets.items.length});
    if (!datasets.items.length) {
      $('datasets').append(node('p',t(access==='connected'?'noConnectedResults':'noDatasets')));
      if(access!=='all'){const all=node('button',t('searchAllData'));all.type='button';all.addEventListener('click',()=>{access='all';searchOffset=0;search();});$('datasets').append(all);}
      $('datasets').append(internalLink('/coverage?q=Plate.hk&access=all',t('tryPlate')),document.createTextNode(' · '),internalLink('/coverage?q=weather&access=all',t('topicWeather'))); return;
    }
    for (const d of datasets.items) {
      const row = node('article', ''), heading=node('h3','');row.className='catalogue-result';
      const connected=d.entryKind==='connected_service';
      const button=node(connected?'a':'button',title(d));
      if(connected){const a=internalLink(d.action.url,title(d));button.href=a.href;}
      else {button.type='button';button.setAttribute('aria-pressed',String(datasetId===d.id));button.addEventListener('click',()=>{resetDataset();datasetId=d.id;datasetTitle=title(d);$('resource-step').hidden=false;syncUrl();resources().then(()=>focusSection('resource-heading'));renderDatasets();});}
      heading.append(button);row.append(heading);
      const description=MhkI18n.lang==='zh'?d.descriptionZhHant||d.description:d.description;if(description)row.append(node('p',String(description).replace(/<[^>]*>/g,' ').slice(0,280)));
      const states=d.resourceSummary?.byStatus||{};
      const capability=connected?'connectedQuery':states.queryable?'previewChecked':states.needs_selection||states.stale?'sourceSettingsNeeded':states.document?'documentPreview':'sourceFiles';
      const badge=node('span',t(capability));badge.className='data-capability';row.append(badge,node('p',`${d.provider} · ${t(d.providerType)} · ${d.catalogue}`));
      if(connected){const a=internalLink(d.action.url,MhkI18n.lang==='zh'?d.action.labelZhHant:d.action.label);a.className='mhk-button mhk-secondary';row.append(a);}
      else row.append(node('p',t('sourceCount',{total:d.resourceSummary?.total??'—'})));
      row.append(link(d.sourceUrl,t('originalSource')));$('datasets').append(row);
    }
    $('datasets-next').hidden = datasets.nextOffset == null; $('datasets-next').dataset.offset = datasets.nextOffset;
  }
  async function search({readInput=true,push=true}={}) {
    if(readInput)submittedQuery=$('dataset-query').value.trim();
    resetDataset();syncUrl(push);
    const sequence = ++searchSequence; datasets = null; searchError = null; $('dataset-total').textContent = ''; $('datasets-next').hidden = true; renderDatasets();
    try {
      const data = await api('/api/v1/catalogue/datasets?' + new URLSearchParams({q:submittedQuery,access,limit:10,offset:searchOffset}));
      if (sequence !== searchSequence) return; datasets = data;
    } catch (e) { if (sequence !== searchSequence) return; searchError = e; }
    renderDatasets();
  }
  function renderSelection() {
    if (!selected) { $('selected-resource').textContent = t('noResource'); return; }
    $('selected-resource').replaceChildren(node('strong',datasetTitle || selected.datasetId),node('span', ` · ${selected.aliases?.[0]?.name || selected.format} · `), link(selected.url, t('originalSource')));
  }
  function renderResources() {
    clearTimeout(expiryTimer); expiryTimer = null;
    if (!datasetId && !directoryMode) { $('resources').textContent = resourceError ? failure(resourceError) : t('searchFirst'); return; }
    $('resources').replaceChildren();$('dataset-context').textContent=datasetTitle;
    if (!resourceList) { $('resources').textContent = resourceError ? failure(resourceError) : t('loadingResources'); return; }
    if(resourceList.connected){const d=resourceList.connected;$('resources').append(node('p',t('connectedAccessHint')),internalLink(d.action.url,MhkI18n.lang==='zh'?d.action.labelZhHant:d.action.label));return;}
    $('resources').append(node('p', t('resourceMatches', {total:resourceList.total,shown:resourceList.items.length})));
    for (const r of resourceList.items) {
      const row = node('article', ''), button = node('button', `${r.aliases?.[0]?.name || r.datasetId} · ${r.format}`); button.type = 'button';
      button.setAttribute('aria-pressed',String(selected?.id===r.id));
      button.addEventListener('click',()=>selectResource(r));

      const v = r.validation;
      const expired = r.transport?.operation === 'arrivals' && v.status === 'queryable' && Date.now() >= (v.lastValidatedAt + r.transport.cacheTTLSeconds) * 1000;
      if (r.transport) {
        row.append(node('p',t(r.transport.operation === 'arrivals' ? 'transportFeed' : 'transportReference', {operator:r.transport.operator,seconds:r.transport.cacheTTLSeconds})));
        if (r.transport.requiredParameters.length) row.append(node('p',t('transportInputs',{parameters:r.transport.requiredParameters.join(', ')})));
      }
      const reason = r.transport && v.reason === 'SOURCE_NOT_FOUND' ? t('transportEndpointMissing') : v.reason;
      row.append(button, node('p', `${r.catalogue} · ${t(r.transport?.operation === 'arrivals' && (v.status === 'stale' || expired) ? 'transportRefreshDue' : v.status)}${reason ? ' · ' + reason : ''} · ${t('lastCheck')}: ${v.lastCheckedAt ? new Date(v.lastCheckedAt*1000).toLocaleString(MhkI18n.locale,{timeZone:'Asia/Hong_Kong',hour12:false})+' HKT' : t('pending')}`), link(r.url, t('sourceLink')));
      if(r.validation.freshness?.cacheExpired && r.validation.status==='queryable')row.append(node('p',t('validationRefreshDue')));
      if(r.transport?.alternative){const alt=r.transport.alternative;row.append(alt.resourceId ? internalLink('/coverage?'+new URLSearchParams({dataset:'hk-td-wcms_8-ferry-services-tt-ft',resource:alt.resourceId,access:'sources'}),t('publishedTimetable')) : link(alt.url,t('publishedTimetable')));}
      $('resources').append(row);
    }
    $('resources-next').hidden = resourceList.nextOffset == null; $('resources-next').dataset.offset = resourceList.nextOffset;
    const deadlines = resourceList.items.filter(r => r.transport?.operation === 'arrivals' && r.validation.status === 'queryable').map(r => (r.validation.lastValidatedAt + r.transport.cacheTTLSeconds) * 1000 - Date.now()).filter(ms => ms > 0);
    if (deadlines.length) expiryTimer = setTimeout(renderResources, Math.min(...deadlines) + 25);
  }
  function selectResource(r,push=true) {
    resetPreview();selected=r;$('preview-step').hidden=false;renderSourceInputs();renderSelection();renderQuery();syncUrl(push);
    $('resource-code').textContent=`GET ${location.origin}/api/v1/resources/${r.id}/schema\n\nMCP: hk_resource_schema(${JSON.stringify({resourceId:r.id})})`;renderResources();focusSection('query-heading');
  }
  function renderSourceInputs(names=selected?.transport?.requiredParameters||[]) {
    const box=$('source-inputs'), previous={};box.querySelectorAll('[data-source-parameter]').forEach(e=>previous[e.dataset.sourceParameter]=e.value);box.replaceChildren();
    if(!names.length)return;box.append(node('p',t('sourceInputHelp')));
    for(const name of names){const label=node('label',t('param_'+name)===('param_'+name)?name:t('param_'+name));const input=node('input','');input.dataset.sourceParameter=name;input.setAttribute('aria-label',label.textContent);input.maxLength=40;input.value=previous[name]??selected?.transport?.parameterExamples?.[name]??'';label.append(input);box.append(label);}
  }
  async function resources() {
    const sequence = ++resourceSequence; resourceList = null; resourceError = null; $('resources-next').hidden = true; renderResources();
    try {
      const params = {limit:15,offset:resourceOffset};
      if ($('resource-format').value) params.format = $('resource-format').value;
      if (!directoryMode) params.datasetId = datasetId;
      if (directoryMode && $('coverage-status').value) params.status = $('coverage-status').value;
      const data = await api('/api/v1/resources?' + new URLSearchParams(params));
      if (sequence !== resourceSequence) return; resourceList = data;
    } catch (e) { if (sequence !== resourceSequence) return; resourceError = e; }
    renderResources();
  }
  function renderQuery() {
    $('record-path-choices').querySelectorAll('select').forEach(e=>e.disabled=busy);
    $('record-query').querySelectorAll('button').forEach(button => { button.disabled = !selected || busy; });
    $('record-table').replaceChildren(); $('resource-citations').replaceChildren();
    if (queryError) { $('query-message').textContent = failure(queryError); return; }
    if (busy) { $('query-message').textContent = t('readingSource'); return; }
    if (!result) { $('query-message').textContent = selected ? t('inspectHint') : ''; return; }
    $('record-response').textContent = JSON.stringify(result,null,2);
    if (result.selectionRequired) {
      if(result.selectionRequired==='parameters')renderSourceInputs(result.parameters||[]);else $('query-options').open=true;
      $('query-message').textContent = t('chooseSelection',{kind:t(result.selectionRequired)}) + (result.selectionRequired==='parameters'?'':JSON.stringify(result.layers || result.featureTypes || result.sheets || result.parameters)); return;
    }
    if (result.data) {
      const items = result.data.items, calendar=result.schema?.scope==='calendar_events', fields = calendar?['dtstart','summary']:[...new Set(items.flatMap(Object.keys))].slice(0,12);
      const table = node('table',''), thead = node('thead',''), tr = node('tr',''); fields.forEach(f => tr.append(node('th',calendar?t(f==='summary'?'holidayName':'holidayDate'):f))); thead.append(tr); table.append(thead);
      const tbody = node('tbody','');
      for (const item of items) {
        const row = node('tr','');
        fields.forEach(f => {
          const value = item[f], cell = node('td','');
          if(calendar && f==='dtstart' && Array.isArray(value) && value[1]?.value==='DATE' && /^\d{8}$/.test(value[0]))cell.textContent=value[0].slice(0,4)+'-'+value[0].slice(4,6)+'-'+value[0].slice(6,8);
          else if (value && typeof value === 'object') {
            const details = node('details','');
            details.append(node('summary', t(Array.isArray(value) ? 'nestedItems' : 'nestedFields', {total:Object.keys(value).length})), node('pre',JSON.stringify(value,null,2)));
            cell.append(details);
          } else cell.textContent = value == null ? '—' : String(value);
          row.append(cell);
        });
        tbody.append(row);
      }
      table.append(tbody); const wrap = node('div',''); wrap.className = 'table-scroll'; wrap.append(table); $('record-table').append(wrap);
      $('query-message').textContent = t('matchedRecords',{total:result.meta.total,shown:items.length}) + (!items.length ? ' · '+t('noMatches') : '') + (result.meta.structuredQueryable ? '' : ' · '+t('unverifiedText')) + (result.warnings.length ? ' · '+result.warnings.map(w=>w.code).join(', ') : '');
    } else { $('query-message').textContent = t('schemaSummary',{total:result.recordCount,scope:result.schema.scope,fields:result.schema.fields.map(f=>f.name).join(', ')}); }
    renderRecordPaths();
    if (result.quality?.semanticVerification==='not_performed') $('resource-citations').append(node('p',t('rawSourceQualification')));
    if (result.schema?.transport?.sourceTimestamp) $('resource-citations').append(node('p',t('transportSnapshot',{time:result.schema.transport.sourceTimestamp})));
    for (const p of result.provenance) $('resource-citations').append(link(p.sourceUrl,p.attribution+' ↗'),node('p',`${t('validated')}: ${new Date(p.lastValidatedAt*1000).toLocaleString(MhkI18n.locale,{timeZone:'Asia/Hong_Kong',hour12:false})+' HKT'} · ${t('publication')}: ${p.publicationDate || t('notSupplied')} · ${t('referencePeriod')}: ${p.referencePeriod || t('notSupplied')}`),link(p.termsUrl,t('sourceTerms')));
    $('records-next').hidden = !nextRecords;
  }
  function renderRecordPaths(){
    const box=$('record-path-choices');box.replaceChildren();const paths=result?.schema?.availableRecordPaths||[];if(paths.length<2||selected?.transport?.operation==='arrivals')return;
    const label=node('label',t('recordListChoice')),select=node('select','');select.setAttribute('aria-label',t('recordListChoice'));for(const path of paths){const option=node('option',path||t('wholeSource'));option.value=path;option.selected=path===result.schema.recordPath;select.append(option);}label.append(select);box.append(label);select.addEventListener('change',()=>{$('record-query').elements.recordPath.value=select.value;query('query');});
  }
  async function query(kind, continuation = false) {
    if (!selected || busy) { if (!selected) $('query-message').textContent = t('selectFirst'); return; }
    const generation = ++requestGeneration; busy = true; queryError = null; $('records-next').hidden = true; renderQuery();
    try {
      const form = new FormData($('record-query')), selectors = {recordPath:form.get('recordPath'),sheet:form.get('sheet')};
      if (form.get('layer') !== '') selectors.layer = Number(form.get('layer'));
      const parameters=JSON.parse(form.get('parameters'));$('source-inputs').querySelectorAll('[data-source-parameter]').forEach(e=>parameters[e.dataset.sourceParameter]=e.value);
      const body = kind === 'schema' ? {...selectors,parameters} : continuation ? {...lastQuery,offset:nextRecords.offset,version:nextRecords.version} : {...selectors,parameters,filters:JSON.parse(form.get('filters')),fields:String(form.get('fields')).split(',').map(s=>s.trim()).filter(Boolean),limit:20};
      const path = `/api/v1/resources/${selected.id}/` + (kind === 'schema' ? 'schema' : 'query');
      const data = await api(path,body);
      if (generation !== requestGeneration) return;
      result = data; lastQuery = body; nextRecords = result.meta?.nextOffset == null ? null : {offset:result.meta.nextOffset,version:result.meta.version};
      $('resource-code').textContent = `POST ${location.origin}${path}\n${JSON.stringify(body,null,2)}\n\nMCP: ${kind === 'schema' ? 'hk_resource_schema' : 'hk_resource_query'}(${JSON.stringify({resourceId:selected.id,...body},null,2)})`;
      coverage();
    } catch (e) { if (generation !== requestGeneration) return; result=null;queryError=e;
      if(/PARAMETERS_REQUIRED/.test(e.message)){try{const discovery=await api(`/api/v1/resources/${selected.id}/schema`);if(generation===requestGeneration){result=discovery;queryError=null;}}catch{}}
      if(/SHEET_REQUIRED|INVALID_SHEET|LAYER_REQUIRED|INVALID_RECORD_PATH/.test(e.message))$('query-options').open=true;
    } finally { if(generation===requestGeneration){busy=false;renderQuery();if(datasetId||directoryMode)resources();} }
  }
  function render() { MhkI18n.apply(); if (!selected) $('resource-code').textContent = t('selectForCode'); if (document.documentElement?.dataset?.discovery !== 'true') document.title = t('coveragePageTitle'); renderCoverage(); renderDatasets(); renderResources(); renderSelection(); renderQuery(); }
  async function restore() {
    const p=new URL(location.href).searchParams, wantedDataset=p.get('dataset'), wantedResource=p.get('resource'), wantedOffset=Math.min(100000,Math.max(0,Number(p.get('sourceOffset'))||0)),wantedFormat=p.get('format')||'';
    submittedQuery=p.get('q')||'';access=['all','connected','sources'].includes(p.get('access'))?p.get('access'):(submittedQuery||wantedDataset?'all':'connected');searchOffset=Math.min(100000,Math.max(0,Number(p.get('offset'))||0));$('dataset-query').value=submittedQuery;
    const pending=search({readInput:false,push:false}),sequence=searchSequence;await pending;
    if(sequence!==searchSequence||!wantedDataset)return;
    try{const d=await api('/api/v1/catalogue/datasets/'+encodeURIComponent(wantedDataset));if(sequence!==searchSequence)return;datasetId=d.id;datasetTitle=title(d);resourceOffset=wantedOffset;$('resource-format').value=wantedFormat;$('resource-step').hidden=false;await resources();if(sequence!==searchSequence)return;
      if(wantedResource){const r=resourceList?.items.find(r=>r.id===wantedResource);if(r)selectResource(r,false);}syncUrl(false);renderDatasets();
    }catch(e){if(sequence===searchSequence){resourceError=e;$('resource-step').hidden=false;renderResources();}}
  }
  $('dataset-search').addEventListener('submit',e=>{e.preventDefault();searchOffset=0;access='all';search();});
  document.querySelectorAll('[data-access]').forEach(b=>b.addEventListener('click',()=>{access=b.dataset.access;searchOffset=0;search();}));
  $('datasets-next').addEventListener('click',e=>{searchOffset=Number(e.target.dataset.offset);search();});
  $('directory').addEventListener('click',()=>{resetDataset();directoryMode=true;$('resource-step').hidden=false;syncUrl();resources();});
  $('resource-format').addEventListener('change',()=>{resetPreview();resourceOffset=0;syncUrl();if(datasetId||directoryMode)resources();});
  $('resources-next').addEventListener('click',e=>{resetPreview();resourceOffset=Number(e.target.dataset.offset);syncUrl();resources();});
  $('record-query').addEventListener('submit',e=>{e.preventDefault();query(e.submitter?.value||'query');});
  $('records-next').addEventListener('click',()=>query('query',true));
  window.addEventListener('popstate',restore);window.addEventListener('mhk:language',()=>{render();if(selected)renderSourceInputs(result?.parameters||selected.transport?.requiredParameters||[]);});
  render();coverage();restore();
})();
