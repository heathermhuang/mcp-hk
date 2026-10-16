import {fetchPublicJson} from './http.js';
/* Source data is always rendered as text and retains its original language. */
(() => {
  const $ = id => document.getElementById(id), t = (...args) => MhkI18n.t(...args);
  let searchSequence = 0, resourceSequence = 0, requestGeneration = 0;
  let selected = null, nextRecords = null, lastQuery = null, searchOffset = 0, resourceOffset = 0;
  let datasetId = null, directoryMode = false, busy = false;
  let inventory = null, inventoryFailed = false, datasets = null, resourceList = null, result = null;
  let searchError = null, resourceError = null, queryError = null;
  const api = fetchPublicJson;
  const node = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
  function link(url, title) { const a = node('a', title); if (/^https?:\/\//i.test(url)) { a.href = url; a.rel = 'noreferrer'; } return a; }
  function failure(error) { return MhkI18n.lang === 'en' ? error.message : `${t(error instanceof SyntaxError ? 'invalidJson' : 'sourceError')} (${error.message.split(':')[0].slice(0,80)})`; }
  function renderCoverage() {
    MhkI18n.coverageSummary($('coverage-summary'), inventory, inventoryFailed);
    if (inventory) $('coverage-detail').textContent = JSON.stringify(inventory, null, 2);
  }
  async function coverage() {
    try { inventory = await api('/api/v1/coverage'); inventoryFailed = false; } catch { inventoryFailed = true; }
    renderCoverage();
  }
  function renderDatasets() {
    $('datasets').replaceChildren();
    if (!datasets) { $('datasets').textContent = searchError ? failure(searchError) : t('searching'); return; }
    $('dataset-total').textContent = t('datasetMatches', {total: datasets.total, shown: datasets.items.length});
    if (!datasets.items.length) $('datasets').textContent = t('noDatasets');
    for (const d of datasets.items) {
      const row = node('article', ''), button = node('button', d.title || d.id); button.type = 'button';
      button.addEventListener('click', () => { datasetId = d.id; directoryMode = false; resourceOffset = 0; resources(); });
      row.append(button, node('p', `${d.provider} · ${t(d.providerType)} · ${d.catalogue}`), link(d.sourceUrl, t('originalCatalogue'))); $('datasets').append(row);
    }
    $('datasets-next').hidden = datasets.nextOffset == null; $('datasets-next').dataset.offset = datasets.nextOffset;
  }
  async function search() {
    const sequence = ++searchSequence; datasets = null; searchError = null; $('dataset-total').textContent = ''; $('datasets-next').hidden = true; renderDatasets();
    try {
      const data = await api('/api/v1/catalogue/datasets?' + new URLSearchParams({q: $('dataset-query').value, limit: 10, offset: searchOffset}));
      if (sequence !== searchSequence) return; datasets = data;
    } catch (e) { if (sequence !== searchSequence) return; searchError = e; }
    renderDatasets();
  }
  function renderSelection() {
    if (!selected) { $('selected-resource').textContent = t('noResource'); return; }
    $('selected-resource').replaceChildren(node('span', `${selected.datasetId} · ${selected.format} · `), link(selected.url, t('originalSource')));
  }
  function renderResources() {
    if (!datasetId && !directoryMode) { $('resources').textContent = t('searchFirst'); return; }
    $('resources').replaceChildren();
    if (!resourceList) { $('resources').textContent = resourceError ? failure(resourceError) : t('loadingResources'); return; }
    $('resources').append(node('p', t('resourceMatches', {total:resourceList.total,shown:resourceList.items.length})));
    for (const r of resourceList.items) {
      const row = node('article', ''), button = node('button', `${r.aliases?.[0]?.name || r.datasetId} · ${r.format}`); button.type = 'button';
      button.addEventListener('click', () => {
        selected = r; ++requestGeneration; nextRecords = null; lastQuery = null; result = null; queryError = null;
        $('record-table').replaceChildren(); $('record-response').textContent = ''; $('resource-citations').replaceChildren(); $('records-next').hidden = true;
        renderSelection(); renderQuery();
        $('resource-code').textContent = `GET ${location.origin}/api/v1/resources/${r.id}/schema\n\nMCP: hk_resource_schema({"resourceId":"${r.id}"})`;
        $('selected-resource').scrollIntoView({behavior:'smooth',block:'center'});
      });
      const v = r.validation;
      row.append(button, node('p', `${r.catalogue} · ${t(v.status)}${v.reason ? ' · ' + v.reason : ''} · ${t('lastCheck')}: ${v.lastCheckedAt ? new Date(v.lastCheckedAt * 1000).toISOString() : t('pending')}`), link(r.url, t('sourceLink'))); $('resources').append(row);
    }
    $('resources-next').hidden = resourceList.nextOffset == null; $('resources-next').dataset.offset = resourceList.nextOffset;
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
    $('record-table').replaceChildren(); $('resource-citations').replaceChildren();
    if (queryError) { $('query-message').textContent = failure(queryError); return; }
    if (busy) { $('query-message').textContent = t('readingSource'); return; }
    if (!result) { $('query-message').textContent = selected ? t('inspectHint') : ''; return; }
    $('record-response').textContent = JSON.stringify(result,null,2);
    if (result.selectionRequired) {
      $('query-message').textContent = t('chooseSelection',{kind:t(result.selectionRequired)}) + JSON.stringify(result.layers || result.featureTypes || result.sheets || result.parameters); return;
    }
    if (result.data) {
      const items = result.data.items, fields = [...new Set(items.flatMap(Object.keys))].slice(0,12);
      const table = node('table',''), thead = node('thead',''), tr = node('tr',''); fields.forEach(f => tr.append(node('th',f))); thead.append(tr); table.append(thead);
      const tbody = node('tbody','');
      for (const item of items) { const row = node('tr',''); fields.forEach(f => row.append(node('td',item[f] == null ? '—' : typeof item[f] === 'object' ? JSON.stringify(item[f]) : String(item[f])))); tbody.append(row); }
      table.append(tbody); const wrap = node('div',''); wrap.className = 'table-scroll'; wrap.append(table); $('record-table').append(wrap);
      $('query-message').textContent = t('matchedRecords',{total:result.meta.total,shown:items.length}) + (!items.length ? ' · '+t('noMatches') : '') + (result.meta.structuredQueryable ? '' : ' · '+t('unverifiedText')) + (result.warnings.length ? ' · '+result.warnings.map(w=>w.code).join(', ') : '');
    } else { $('query-message').textContent = t('schemaSummary',{total:result.recordCount,scope:result.schema.scope,fields:result.schema.fields.map(f=>f.name).join(', ')}); }
    for (const p of result.provenance) $('resource-citations').append(link(p.sourceUrl,p.attribution+' ↗'),node('p',`${t('validated')}: ${new Date(p.lastValidatedAt*1000).toISOString()} · ${t('publication')}: ${p.publicationDate || t('notSupplied')} · ${t('referencePeriod')}: ${p.referencePeriod || t('notSupplied')}`),link(p.termsUrl,t('sourceTerms')));
    $('records-next').hidden = !nextRecords;
  }
  async function query(kind, continuation = false) {
    if (!selected || busy) { if (!selected) $('query-message').textContent = t('selectFirst'); return; }
    const generation = ++requestGeneration; busy = true; queryError = null; $('records-next').hidden = true; renderQuery();
    try {
      const form = new FormData($('record-query')), selectors = {recordPath:form.get('recordPath'),sheet:form.get('sheet')};
      if (form.get('layer') !== '') selectors.layer = Number(form.get('layer'));
      const body = kind === 'schema' ? {...selectors,parameters:JSON.parse(form.get('parameters'))} : continuation ? {...lastQuery,offset:nextRecords.offset,version:nextRecords.version} : {...selectors,parameters:JSON.parse(form.get('parameters')),filters:JSON.parse(form.get('filters')),fields:String(form.get('fields')).split(',').map(s=>s.trim()).filter(Boolean),limit:20};
      const path = `/api/v1/resources/${selected.id}/` + (kind === 'schema' ? 'schema' : 'query');
      const data = await api(path,body);
      if (generation !== requestGeneration) return;
      result = data; lastQuery = body; nextRecords = result.meta?.nextOffset == null ? null : {offset:result.meta.nextOffset,version:result.meta.version};
      $('resource-code').textContent = `POST ${location.origin}${path}\n${JSON.stringify(body,null,2)}\n\nMCP: ${kind === 'schema' ? 'hk_resource_schema' : 'hk_resource_query'}(${JSON.stringify({resourceId:selected.id,...body},null,2)})`;
      coverage();
    } catch (e) { if (generation !== requestGeneration) return; result = null; queryError = e; }
    finally { busy = false; renderQuery(); }
  }
  function render() { MhkI18n.apply(); if (!selected) $('resource-code').textContent = t('selectForCode'); document.title = t('coveragePageTitle'); renderCoverage(); renderDatasets(); renderResources(); renderSelection(); renderQuery(); }
  $('dataset-query').value = new URL(location.href).searchParams.get('q') || 'public holidays';
  $('dataset-search').addEventListener('submit',e=>{e.preventDefault();searchOffset=0;search();});
  $('datasets-next').addEventListener('click',e=>{searchOffset=Number(e.target.dataset.offset);search();});
  $('directory').addEventListener('click',()=>{directoryMode=true;resourceOffset=0;resources();});
  $('resource-format').addEventListener('change',()=>{resourceOffset=0;if(datasetId || directoryMode)resources();});
  $('resources-next').addEventListener('click',e=>{resourceOffset=Number(e.target.dataset.offset);resources();});
  $('record-query').addEventListener('submit',e=>{e.preventDefault();query(e.submitter?.value || 'query');});
  $('records-next').addEventListener('click',()=>query('query',true));
  window.addEventListener('mhk:language',render);
  render(); coverage(); search();
})();
