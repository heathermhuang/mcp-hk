/* No model calls or demo fixtures: every displayed record comes from the API. */
(() => {
  const root = document.getElementById('mhk-preview');
  let state = {screen: location.pathname === '/plates' ? 'plates' : location.pathname === '/sources' ? 'sources' : location.pathname === '/demo' ? 'explore' : location.pathname === '/connect' ? 'connect' : 'home', lang: MhkI18n.lang, radius: 500, code: 'http'};
  let clientKind = 'codex';
  let selected = null, response = null, population = null, requestQuery = '', pending = false;
  let generation = 0;
  let plateResult = null, platePending = false, plateError = '', plateRequest = null;
  let plateGeneration = 0;
  const $ = selector => root.querySelector(selector);
  const label = value => value?.[state.lang === 'en' ? 'en' : 'zhHant'] || value?.en || value?.zhHant || '—';
  $('#mhk-discovery-form').addEventListener('submit', e => {
    e.preventDefault();
    location.assign('/coverage?' + new URLSearchParams({q:$('#mhk-discovery-query').value.trim(),access:'all',lang:MhkI18n.locale}));
  });

  function error(message) { $('#mhk-error').hidden = !message; $('#mhk-error').textContent = message || ''; }
  async function api(path, signal) {
    const {fetchPublicJson} = await import('./http.js');
    return fetchPublicJson(path);
  }
  function render() {
    root.querySelectorAll('[data-page]').forEach(e => e.hidden = e.dataset.page !== state.screen);
    root.querySelectorAll('[data-screen]').forEach(e => { if (e.dataset.screen === state.screen) e.setAttribute('aria-current', 'page'); else e.removeAttribute('aria-current'); });
    MhkI18n.apply();
    document.title = MhkI18n.t(state.screen + 'PageTitle');
    renderCoverage();
    renderStatus();
    if (state.screen === 'sources' && !statusStarted) { statusStarted = true; status(); }
    const endpoint = location.origin + '/mcp';
    $('[data-dynamic=endpoint]').textContent = endpoint;
    const examples = {codex: `[mcp_servers."mcp.hk"]\nurl = "${endpoint}"\nstartup_timeout_sec = 120`, claude: `claude mcp add --transport http mcp-hk ${endpoint}`, cursor: JSON.stringify({mcpServers: {'mcp.hk': {url: endpoint}}}, null, 2)};
    $('#mhk-install').textContent = examples[clientKind];
    $('#mhk-client-help').textContent = MhkI18n.t('help_' + clientKind);
    root.querySelectorAll('[data-client]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.client === clientKind)));
    $('#mhk-radius').value = String(state.radius);
    $('#mhk-address-form button').disabled = pending;
    $('.mhk-found').hidden = !selected;
    if (selected) {
      $('[data-dynamic=address]').textContent = label(selected.address);
      const districtName = population ? label(population.data.name) : selected.districtId || MhkI18n.t('districtUnavailable');
      $('.mhk-found small').textContent = districtName;
    }
    $('.mhk-explore-grid').hidden = !selected;
    $('.mhk-pop').hidden = !selected;
    const list = $('.mhk-results'); list.replaceChildren();
    for (const [i, record] of (response?.data.items || []).entries()) {
      const row = document.createElement('div'); row.className = 'mhk-result';
      const index = document.createElement('span'); index.className = 'mhk-index'; index.textContent = String(i + 1).padStart(2, '0');
      const names = document.createElement('div');
      const name = document.createElement('div'); name.className = 'mhk-result-name'; name.textContent = label(record.name);
      const detail = document.createElement('div'); detail.className = 'mhk-result-sub'; detail.textContent = `${record.licenceType} · ${label(record.address)}`;
      names.append(name, detail);
      const d = document.createElement('span'); d.className = 'mhk-distance'; d.textContent = record.distanceM == null ? '—' : `${Math.round(record.distanceM)} m`;
      row.append(index, names, d); list.append(row);
    }
    if (response && !response.data.items.length) {
      const empty = document.createElement('p'); empty.textContent = state.lang === 'en' ? 'No licence records in this radius.' : '此範圍內沒有牌照記錄。'; list.append(empty);
    }
    const summary = response?.data.summary;
    $('[data-dynamic=count]').textContent = summary ? `${summary.totalMatched} ${state.lang === 'en' ? 'matching licences · straight-line distance' : '項符合條件的牌照 · 直線距離'}${response.meta.truncated ? ' · ' + response.data.items.length + (state.lang === 'en' ? ' shown' : ' 項已顯示') : ''}` : pending ? MhkI18n.t('loading') : '';
    if (summary?.spatialCoverage.unlocatedCount) $('[data-dynamic=count]').textContent += ` · ${summary.spatialCoverage.unlocatedCount} ${MhkI18n.t('unlocated')}`;
    const more = $('#mhk-more'); more.hidden = !response?.meta.nextCursor; more.disabled = pending;
    more.textContent = state.lang === 'en' ? 'Load more' : '載入更多';
    $('[data-dynamic=groups]').textContent = (summary?.byLicenceType || []).map(g => `${g.licenceType}: ${g.count}`).join(' · ');
    const warnings = [...(response?.warnings || []), ...(population?.warnings || [])];
    $('#mhk-warnings').hidden = !warnings.length;
    $('#mhk-warnings').textContent = warnings.map(w => `${w.code}: ${w.message}`).join(' · ');
    $('.mhk-pop-value').textContent = population ? population.data.population.toLocaleString(state.lang === 'en' ? 'en-HK' : 'zh-HK') : '—';
    $('[data-dynamic=year]').textContent = population?.data.referencePeriod || '—';
    if (selected && !population && !pending) $('[data-i18n=populationNote]').textContent = state.lang === 'en' ? 'District statistic unavailable for this selected address.' : '此地址所屬地區的統計資料暫時不可用。';
    if (population) $('[data-i18n=populationNote]').textContent = `${translations[state.lang].populationNote} ${population.data.areaKm2} km² · ${population.data.populationDensity.toLocaleString()} ${MhkI18n.t('personsKm')}`;
    root.querySelectorAll('[data-code]').forEach(e => e.setAttribute('aria-pressed', String(e.dataset.code === state.code)));
    let code = `GET ${location.origin}/api/v1/restaurants?${requestQuery || 'lat=…&lon=…&includeSummary=true'}`;
    if (state.code === 'mcp') code = JSON.stringify({tool: 'hk_restaurant_search', arguments: selected ? {lat: selected.latitude, lon: selected.longitude, radiusM: state.radius, includeSummary: true, lang: state.lang === 'en' ? 'en' : 'zh-Hant'} : {}}, null, 2);
    if (state.code === 'json') code = JSON.stringify(response || {state: MhkI18n.t('chooseAddress')}, null, 2);
    $('[data-dynamic=code]').textContent = code;
    const provenance = [ ...(response?.provenance || []), ...(population?.provenance || []) ];
    const sourceBox = $('.mhk-code-source'); sourceBox.replaceChildren();
    for (const p of provenance) {
      const line = document.createElement('p');
      const a = document.createElement('a'); a.href = p.sourceUrl; a.textContent = p.attribution; a.rel = 'noreferrer';
      const stamp = document.createElement('span'); stamp.textContent = ` · ${MhkI18n.t('checked')} ${p.lastCheckedAt}${p.stale ? ' · ' + MhkI18n.t('stale') : ''}${p.referencePeriod ? ` · ${MhkI18n.t('year')} ${p.referencePeriod}` : ''}`;
      line.append(a, stamp); sourceBox.append(line);
    }
    if (!provenance.length) sourceBox.textContent = translations[state.lang].provenanceLabel;
    renderPlates();
  }

  function renderPlates() {
    const data = plateResult?.data;
    $('#mhk-plate-form').querySelectorAll('button').forEach(b => b.disabled = platePending);
    const msg = $('#mhk-plate-message');
    msg.textContent = plateError || (platePending ? (state.lang === 'en' ? 'Reading Plate.hk…' : '正在讀取 Plate.hk…') : '');
    const box = $('#mhk-plate-results'); box.replaceChildren();
    if (data) {
      const summary = document.createElement('p');
      summary.textContent = data.method ? `${data.sampleSize ?? '—'} ${state.lang === 'en' ? 'comparable plates' : '個相近車牌'} · ${data.dateFrom || '—'} → ${data.dateTo || '—'}` : `${data.total} ${state.lang === 'en' ? 'historical records' : '項歷史紀錄'} · ${data.query}`;
      box.append(summary);
      if (data.method) {
        const method = document.createElement('p'); method.className = 'mhk-note'; method.textContent = data.method; box.append(method);
        const stats = document.createElement('p');
        stats.textContent = data.statistics ? `${MhkI18n.t('historicalHkd')} · P25 ${data.statistics.p25.toLocaleString()} · ${MhkI18n.t('median')} ${data.statistics.median.toLocaleString()} · P75 ${data.statistics.p75.toLocaleString()}` : (state.lang === 'en' ? 'No qualified historical price distribution.' : '未有足夠成交紀錄作比較。');
        box.append(stats);
      }
      for (const record of data.items) {
        const row = document.createElement('article'); row.className = 'mhk-plate-record';
        const mark = document.createElement('strong');
        mark.textContent = Array.isArray(record.double_line) ? record.double_line.join('\n') : record.double_line || record.single_line;
        const context = document.createElement('p');
        const dateLabel = record.auction_date_label || (record.date_precision === 'year_range' ? record.year_range : record.auction_date) || '—';
        context.textContent = `${dateLabel} · ${MhkI18n.t({pvrm:'pvrm',tvrm_physical:'tvrmPhysical',tvrm_eauction:'tvrmEauction',tvrm_legacy:'tvrmLegacy'}[record.dataset_key] || record.dataset_key)}${record.result_status ? ' · ' + record.result_status : ''}`;
        const amount = document.createElement('span');
        amount.textContent = record.amount_hkd == null ? (state.lang === 'en' ? 'No recorded amount' : '未有記錄金額') : `HK$${record.amount_hkd.toLocaleString()}`;
        const links = document.createElement('p');
        for (const [url, title] of [[record.pdf_url || record.source_url, state.lang === 'en' ? 'Original source ↗' : '原始來源 ↗'], [record.detailUrl, 'Plate.hk ↗']]) {
          if (!url) continue;
          const a = document.createElement('a'); a.href = url; a.textContent = title; a.rel = 'noreferrer'; links.append(a, ' ');
        }
        row.append(mark, amount, context, links); box.append(row);
      }
      if (!data.items.length) {
        const empty = document.createElement('p'); empty.textContent = state.lang === 'en' ? 'No historical records matched. This does not establish availability.' : '找不到相關拍賣紀錄，並不代表此車牌可供購買。'; box.append(empty);
      }
    }
    const more = $('#mhk-plate-more'); more.hidden = !data?.nextPage; more.disabled = platePending;
    if (plateRequest) {
      const {kind, params} = plateRequest;
      $('#mhk-plate-code').textContent = `GET ${location.origin}/api/v1/plates/${kind}?${new URLSearchParams(params)}\n\nMCP: ${kind === 'search' ? 'hk_plate_search' : 'hk_plate_comparables'}(${JSON.stringify(params, null, 2)})`;
    }
    const p = plateResult?.provenance[0];
    $('#mhk-plate-source').textContent = p ? `${p.attribution} · ${MhkI18n.t('checked')} ${p.lastCheckedAt} · ${MhkI18n.t('fiveMinuteCache')}` : '';
  }

  async function loadPlates(kind, params) {
    const token = ++plateGeneration;
    plateRequest = {kind, params}; platePending = true; plateResult = null; plateError = ''; renderPlates();
    try { const result = await api('/api/v1/plates/' + kind + '?' + new URLSearchParams(params)); if (token === plateGeneration) plateResult = result; }
    catch (e) { if (token === plateGeneration) plateError = e.message; }
    finally { if (token === plateGeneration) { platePending = false; renderPlates(); } }
  }
  $('#mhk-plate-form').addEventListener('submit', e => {
    e.preventDefault();
    const kind = e.submitter?.dataset.kind || 'search';
    const params = {q: $('#mhk-plate-query').value, page: 1, pageSize: 5};
    if (kind === 'search') Object.assign(params, {dataset: $('#mhk-plate-dataset').value, mode: $('#mhk-plate-mode').value, sort: 'date_desc'});
    loadPlates(kind, params);
  });
  $('#mhk-plate-more').addEventListener('click', () => {
    if (!platePending && plateResult?.data.nextPage && plateRequest) loadPlates(plateRequest.kind, {...plateRequest.params, page: plateResult.data.nextPage});
  });

  async function loadNearby() {
    const token = ++generation;
    if (!selected) return;
    if (selected.latitude == null || selected.longitude == null) { error(MhkI18n.t('noCoordinates')); return; }
    pending = true; response = null; population = null; error(''); render();
    requestQuery = new URLSearchParams({lat: selected.latitude, lon: selected.longitude, radiusM: state.radius, includeSummary: 'true', lang: state.lang === 'en' ? 'en' : 'zh-Hant'}).toString();
    const tasks = [api('/api/v1/restaurants?' + requestQuery), selected.districtId ? api('/api/v1/districts/' + encodeURIComponent(selected.districtId) + '/statistics') : Promise.resolve(null)];
    const result = await Promise.allSettled(tasks);
    if (token !== generation) return;
    pending = false;
    if (result[0].status === 'fulfilled') response = result[0].value;
    else error(result[0].reason.message);
    if (result[1].status === 'fulfilled') population = result[1].value;
    render();
  }

  $('#mhk-more').addEventListener('click', async () => {
    if (!response?.meta.nextCursor || pending) return;
    const token = generation, previous = response; pending = true; render();
    try {
      const next = await api('/api/v1/restaurants?' + requestQuery + '&cursor=' + encodeURIComponent(previous.meta.nextCursor));
      if (token !== generation) return;
      response = {...next, data: {...next.data, items: [...previous.data.items, ...next.data.items]}};
    } catch (e) { if (token === generation) error(e.message); }
    finally { if (token === generation) { pending = false; render(); } }
  });
  $('#mhk-address-form').addEventListener('submit', async e => {
    e.preventDefault();
    const token = ++generation;
    selected = null; response = null; population = null; pending = true; error(''); render();
    $('#mhk-candidates').replaceChildren();
    try {
      const result = await api('/api/v1/addresses/search?' + new URLSearchParams({q: $('#mhk-query').value, limit: '5'}));
      if (token !== generation) return;
      if (!result.data.items.length) error(state.lang === 'en' ? 'No source address matched. Try a building name or street number.' : '找不到符合地址，請試用大廈名稱或街道門牌。');
      for (const item of result.data.items) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = label(item.address);
        button.addEventListener('click', () => { selected = item; $('#mhk-candidates').replaceChildren(); loadNearby(); });
        $('#mhk-candidates').append(button);
      }
    } catch (e) { if (token === generation) error(e.message); }
    finally { if (token === generation) { pending = false; render(); } }
  });
  function screenFromPath() { return {'/demo':'explore','/connect':'connect','/plates':'plates','/sources':'sources'}[location.pathname] || 'home'; }
  root.querySelectorAll('[data-screen],[data-go]').forEach(b => b.addEventListener('click', e => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault(); state.screen = b.dataset.screen || b.dataset.go;
    const path = {home:'/',explore:'/demo',connect:'/connect',plates:'/plates',sources:'/sources'}[state.screen];
    history.pushState(null, '', path + '?lang=' + MhkI18n.locale); render(); window.dispatchEvent(new Event('mhk:navigate'));
  }));
  window.addEventListener('popstate', () => { state.screen = screenFromPath(); render(); });
  window.addEventListener('mhk:language', () => { state.lang = MhkI18n.lang; render(); });
  $('#mhk-radius').addEventListener('change', e => { state.radius = Number(e.target.value); loadNearby(); });
  root.querySelectorAll('[data-code]').forEach(b => b.addEventListener('click', () => { state.code = b.dataset.code; render(); }));

  let sourceStatus = null, transportStatus = null, statusError = false, statusStarted = false, inventory = null, inventoryError = false;
  function renderStatus() {
    renderTransportStatus();
    const box = $('#mhk-status'); box.replaceChildren();
    if (!sourceStatus) { box.textContent = MhkI18n.t(statusError ? 'statusUnavailable' : 'loading'); return; }
    for (const source of sourceStatus.sources) {
      const item = document.createElement('article');
      const name = document.createElement('h2'); name.textContent = `${MhkI18n.t('source_' + source.sourceId)} · ${MhkI18n.t(source.providerType === 'independent' ? 'independent' : 'government')}`;
      const status = document.createElement('p'); status.textContent = MhkI18n.t(source.stale ? 'noRecentCheck' : 'recentCheck') + (source.recordCount ? ` · ${source.recordCount.toLocaleString()} ${MhkI18n.t('records')}` : '');
      const detail = document.createElement('p'); detail.className = 'mhk-small'; detail.textContent = `${MhkI18n.t('lastSuccess')}: ${source.lastSuccess || MhkI18n.t('notChecked')} · ${MhkI18n.t('lastError')}: ${source.lastError || MhkI18n.t('none')}`;
      const link = document.createElement('a'); link.href = source.sourceUrl; link.textContent = MhkI18n.t(source.providerType === 'independent' ? 'providerData' : 'officialDataset'); link.rel = 'noreferrer';
      item.append(name, status, detail, link); box.append(item);
    }
  }
  function renderCoverage() { for (const id of ['#mhk-coverage', '#mhk-source-coverage']) MhkI18n.coverageSummary($(id), inventory, inventoryError); }
  function renderTransportStatus() {
    const box=$('#mhk-feed-status');box.replaceChildren();
    if(!transportStatus){box.textContent=MhkI18n.t(statusError?'statusUnavailable':'loading');return;}
    const groups=new Map();for(const r of transportStatus.resources||[]){const states=groups.get(r.operator)||[];states.push(MhkI18n.t(r.status==='stale'?'transportRefreshDue':r.status));groups.set(r.operator,states);}
    const searches={'KMB/LWB':'KMB','Green minibuses':'GMB','Hong Kong & Kowloon Ferry':'HKKF','New Lantao Bus':'NLB'};
    for(const [operator,states] of groups){const row=document.createElement('article'),h=document.createElement('h3'),p=document.createElement('p'),a=document.createElement('a');h.textContent=operator;p.textContent=[...new Set(states)].join(' · ');a.href='/coverage?'+new URLSearchParams({q:searches[operator]||operator,access:'sources',lang:MhkI18n.locale});a.textContent=MhkI18n.t('sourceStatusLink');row.append(h,p,a);box.append(row);}
  }
  async function status() {
    const outcomes=await Promise.allSettled([api('/api/v1/status'),api('/api/v1/coverage')]);
    if(outcomes[0].status==='fulfilled')sourceStatus=outcomes[0].value;else statusError=true;
    if(outcomes[1].status==='fulfilled')transportStatus=outcomes[1].value.realtimeTransport;else statusError=true;
    renderStatus();
  }
  async function coverage() {
    try { inventory = await api('/assets/overview.json'); } catch { inventoryError = true; }
    renderCoverage();
  }
  root.querySelectorAll('[data-client]').forEach(b => b.addEventListener('click', () => { clientKind = b.dataset.client; $('#mhk-copy-status').textContent = ''; render(); }));
  $('#mhk-copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#mhk-install').textContent); $('#mhk-copy-status').textContent = state.lang === 'en' ? ' Copied' : ' 已複製'; } catch { $('#mhk-copy-status').textContent = MhkI18n.t('copyFallback'); } });
  render(); coverage();
})();
