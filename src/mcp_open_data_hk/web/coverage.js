/* Source data is always rendered as text, never executable HTML. */
(() => {
  const $ = id => document.getElementById(id);
  let selected = null, nextRecords = null, lastQuery = null, searchOffset = 0, resourceOffset = 0;
  let datasetId = null, directoryMode = false, requestGeneration = 0, busy = false;
  async function api(path, body) {
    const response = await fetch(path, {method: body ? 'POST' : 'GET', headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    const payload = await response.json();
    if (!response.ok) throw new Error(`${payload.error?.code || response.status}: ${payload.error?.message || 'Source unavailable'}`);
    return payload;
  }
  function node(tag, text) { const e = document.createElement(tag); e.textContent = text; return e; }
  function link(url, title) { const a = node('a', title); if (/^https?:\/\//i.test(url)) { a.href = url; a.rel = 'noreferrer'; } return a; }
  async function coverage() {
    try {
      const c = await api('/api/v1/coverage');
      const counts = node('div', ''); counts.className = 'coverage-counts';
      for (const [value, title] of [[c.datasets.discovered, 'catalogue dataset entries'], [c.resources.discovered, 'canonical resource entries'], [c.resources.byStatus.queryable || 0, 'resources validated queryable'], [c.resources.byStatus.pending || 0, 'resources awaiting validation']]) {
        const item = node('p', title); item.prepend(node('strong', value.toLocaleString())); counts.append(item);
      }
      const msg = node('p', c.claim); $('coverage-summary').replaceChildren(counts, msg);
      $('coverage-detail').textContent = JSON.stringify(c, null, 2);
    } catch (e) { $('coverage-summary').textContent = e.message; }
  }
  async function search() {
    $('datasets').textContent = 'Searching inventory…';
    try {
      const result = await api('/api/v1/catalogue/datasets?' + new URLSearchParams({q: $('dataset-query').value, limit: 10, offset: searchOffset}));
      $('dataset-total').textContent = `${result.total} matching dataset entries · ${result.items.length} on this page`;
      $('datasets').replaceChildren();
      if (!result.items.length) $('datasets').textContent = 'No matching dataset. Try a provider name or another term.';
      for (const d of result.items) {
        const row = node('article', ''); const button = node('button', d.title || d.id); button.type = 'button';
        button.addEventListener('click', () => { datasetId = d.id; directoryMode = false; resourceOffset = 0; resources(); });
        row.append(button, node('p', `${d.provider} · ${d.providerType} · ${d.catalogue}`), link(d.sourceUrl, 'Original catalogue ↗'));
        $('datasets').append(row);
      }
      $('datasets-next').hidden = result.nextOffset == null; $('datasets-next').dataset.offset = result.nextOffset;
    } catch (e) { $('datasets').textContent = e.message; }
  }
  async function resources() {
    $('resources').textContent = 'Loading source resources…';
    try {
      const params = {limit: 15, offset: resourceOffset};
      if (!directoryMode) params.datasetId = datasetId;
      if (directoryMode && $('coverage-status').value) params.status = $('coverage-status').value;
      const result = await api('/api/v1/resources?' + new URLSearchParams(params));
      $('resources').replaceChildren(node('p', `${result.total} resource entries · ${result.items.length} shown`));
      for (const r of result.items) {
        const row = node('article', ''); const button = node('button', `${r.aliases?.[0]?.name || r.datasetId} · ${r.format}`); button.type = 'button';
        button.addEventListener('click', () => {
          selected = r; ++requestGeneration; nextRecords = null; lastQuery = null;
          $('record-table').replaceChildren(); $('record-response').textContent = ''; $('resource-citations').replaceChildren(); $('records-next').hidden = true;
          $('selected-resource').replaceChildren(node('span', `${r.datasetId} · ${r.format} · `), link(r.url, 'Original source ↗'));
          $('query-message').textContent = 'Inspect the schema or query the source. Select a sheet/layer when requested.';
          $('resource-code').textContent = `GET ${location.origin}/api/v1/resources/${r.id}/schema\n\nMCP: hk_resource_schema({"resourceId":"${r.id}"})`;
          $('selected-resource').scrollIntoView({behavior: 'smooth', block: 'center'});
        });
        const v = r.validation;
        row.append(button, node('p', `${r.catalogue} · ${v.status}${v.reason ? ' · ' + v.reason : ''} · last check: ${v.lastCheckedAt ? new Date(v.lastCheckedAt * 1000).toISOString() : 'pending'}`), link(r.url, 'Source ↗'));
        $('resources').append(row);
      }
      $('resources-next').hidden = result.nextOffset == null; $('resources-next').dataset.offset = result.nextOffset;
    } catch (e) { $('resources').textContent = e.message; }
  }
  async function query(kind, continuation = false) {
    if (!selected || busy) { if (!selected) $('query-message').textContent = 'Select a resource first.'; return; }
    const generation = ++requestGeneration; busy = true;
    $('query-message').textContent = 'Reading the source…'; $('records-next').hidden = true;
    try {
      const form = new FormData($('record-query'));
      const selectors = {recordPath: form.get('recordPath'), sheet: form.get('sheet')};
      if (form.get('layer') !== '') selectors.layer = Number(form.get('layer'));
      const body = kind === 'schema' ? {...selectors, parameters: JSON.parse(form.get('parameters'))} : continuation ? {...lastQuery, offset: nextRecords.offset, version: nextRecords.version} : {...selectors, parameters: JSON.parse(form.get('parameters')), filters: JSON.parse(form.get('filters')), fields: String(form.get('fields')).split(',').map(s => s.trim()).filter(Boolean), limit: 20};
      const path = `/api/v1/resources/${selected.id}/` + (kind === 'schema' ? 'schema' : 'query');
      const result = await api(path, body);
      if (generation !== requestGeneration) return;
      if (result.selectionRequired) {
        $('record-response').textContent = JSON.stringify(result, null, 2);
        $('query-message').textContent = `Choose ${result.selectionRequired}: ` + JSON.stringify(result.layers || result.featureTypes || result.sheets || result.parameters);
        return;
      }
      lastQuery = body; nextRecords = result.meta?.nextOffset == null ? null : {offset: result.meta.nextOffset, version: result.meta.version};
      $('record-response').textContent = JSON.stringify(result, null, 2);
      $('record-table').replaceChildren();
      if (result.data) {
        const items = result.data.items;
        const fields = [...new Set(items.flatMap(Object.keys))].slice(0, 12);
        const table = node('table', ''); const thead = node('thead', ''); const tr = node('tr', ''); fields.forEach(f => tr.append(node('th', f))); thead.append(tr); table.append(thead);
        const tbody = node('tbody', '');
        for (const item of items) { const row = node('tr', ''); fields.forEach(f => row.append(node('td', item[f] == null ? '—' : typeof item[f] === 'object' ? JSON.stringify(item[f]) : String(item[f])))); tbody.append(row); }
        table.append(tbody); const wrap = node('div', ''); wrap.className = 'table-scroll'; wrap.append(table); $('record-table').append(wrap);
        $('query-message').textContent = `${result.meta.total} matched records · ${items.length} shown${items.length ? '' : ' · no matches'}${result.meta.structuredQueryable ? '' : ' · unverified document text'}${result.warnings.length ? ' · ' + result.warnings.map(w => w.code).join(', ') : ''}`;
      } else { $('query-message').textContent = `${result.recordCount} records · ${result.schema.scope} · fields: ${result.schema.fields.map(f => f.name).join(', ')}`; }
      $('resource-citations').replaceChildren();
      for (const p of result.provenance) $('resource-citations').append(link(p.sourceUrl, p.attribution + ' ↗'), node('p', `Validated: ${new Date(p.lastValidatedAt * 1000).toISOString()} · publication: ${p.publicationDate || 'not supplied'} · reference period: ${p.referencePeriod || 'not supplied'}`), link(p.termsUrl, 'Source terms ↗'));
      $('records-next').hidden = !nextRecords;
      $('resource-code').textContent = kind === 'schema' ? `POST ${location.origin}${path}\n${JSON.stringify(body,null,2)}\n\nMCP: hk_resource_schema(${JSON.stringify({resourceId:selected.id,...body},null,2)})` : `POST ${location.origin}${path}\n${JSON.stringify(body,null,2)}\n\nMCP: hk_resource_query(${JSON.stringify({resourceId:selected.id,...body},null,2)})`;
      coverage();
    } catch (e) { if (generation === requestGeneration) $('query-message').textContent = e.message; }
    finally { busy = false; }
  }
  $('dataset-search').addEventListener('submit', e => { e.preventDefault(); searchOffset = 0; search(); });
  $('datasets-next').addEventListener('click', e => { searchOffset = Number(e.target.dataset.offset); search(); });
  $('directory').addEventListener('click', () => { directoryMode = true; resourceOffset = 0; resources(); });
  $('resources-next').addEventListener('click', e => { resourceOffset = Number(e.target.dataset.offset); resources(); });
  $('record-query').addEventListener('submit', e => { e.preventDefault(); query(e.submitter?.value || 'query'); });
  $('records-next').addEventListener('click', () => query('query', true));
  coverage(); search();
})();
