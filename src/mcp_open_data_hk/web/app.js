/* No model calls or demo fixtures: every displayed record comes from the API. */
(() => {
  const root = document.getElementById('mhk-preview');
  Object.assign(translations.en, {
    sample: 'EXAMPLE REQUEST', illustrative: 'Official sources · explicit provenance',
    sampleBadge: 'PUBLIC SOURCE DATA', searchLabel: 'LOOK UP A HONG KONG ADDRESS',
    fixtureNote: 'Choose a returned candidate before searching nearby. ALS is not an exhaustive address register.',
    districtAddress: 'Selected source address', populationLabel: 'DISTRICT POPULATION',
    populationNote: 'Published district-wide figure, not population within the search radius.',
    connectionNote: 'Connection URL for this instance. Supported transport: Streamable HTTP; local stdio is also available.',
    previewFooter: 'OPEN-SOURCE DEVELOPMENT BUILD', endpointLabel: 'THIS INSTANCE’S MCP ENDPOINT',
    provenanceLabel: 'Response provenance', getConnected: 'Connect your AI',
    question: '“Find licensed restaurants near this address.”'
  });
  Object.assign(translations.zh, {
    sample: '查詢示例', illustrative: '官方來源 · 清楚標示出處', sampleBadge: '公共來源資料',
    searchLabel: '查詢香港地址', fixtureNote: '請選擇傳回的地址，再搜尋附近食肆。地址服務並非完整地址名冊。',
    districtAddress: '已選來源地址', populationLabel: '地區人口',
    populationNote: '已發表的全區人口，並非搜尋範圍內的人口。',
    connectionNote: '本實例的連接網址。支援 Streamable HTTP，亦可在本機使用 stdio。',
    previewFooter: '開源開發版本', endpointLabel: '本實例的 MCP 端點', provenanceLabel: '回應資料來源'
  });
  let state = {screen: location.pathname === '/sources' ? 'sources' : location.pathname === '/demo' ? 'explore' : location.pathname === '/connect' ? 'connect' : 'home', lang: 'en', radius: 500, code: 'http'};
  let clientKind = 'codex';
  let selected = null, response = null, population = null, requestQuery = '', pending = false;
  let generation = 0;
  const $ = selector => root.querySelector(selector);
  const label = value => value?.[state.lang === 'en' ? 'en' : 'zhHant'] || value?.en || value?.zhHant || '—';

  function error(message) { $('#mhk-error').hidden = !message; $('#mhk-error').textContent = message || ''; }
  async function api(path, signal) {
    const r = await fetch(path, {signal, headers: {'Accept': 'application/json'}});
    const data = await r.json();
    if (!r.ok) throw new Error(`${data.error?.code || r.status}: ${data.error?.message || 'Source unavailable'}`);
    return data;
  }
  function render() {
    root.querySelectorAll('[data-page]').forEach(e => e.hidden = e.dataset.page !== state.screen);
    root.querySelectorAll('[data-screen]').forEach(e => e.setAttribute('aria-pressed', String(e.dataset.screen === state.screen)));
    root.querySelectorAll('[data-i18n]').forEach(e => e.textContent = translations[state.lang][e.dataset.i18n]);
    // Only static, application-owned translated headings contain markup.
    root.querySelectorAll('[data-i18n-html]').forEach(e => e.innerHTML = translations[state.lang][e.dataset.i18nHtml]);
    $('.mhk-language').textContent = state.lang === 'en' ? '繁' : 'EN';
    $('.mhk-language').setAttribute('aria-label', state.lang === 'en' ? 'Switch to Traditional Chinese' : 'Switch to English');
    document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-Hant';
    const endpoint = location.origin + '/mcp';
    $('[data-dynamic=endpoint]').textContent = endpoint;
    const examples = {codex: `codex mcp add hk --url ${endpoint}`, claude: `claude mcp add --transport http hk ${endpoint}`, cursor: JSON.stringify({mcpServers: {hk: {url: endpoint}}}, null, 2)};
    $('#mhk-install').textContent = examples[clientKind];
    $('#mhk-client-help').textContent = clientKind === 'cursor' ? 'Add this to .cursor/mcp.json (project) or ~/.cursor/mcp.json (global).' : 'Run in your terminal, then start or reload the AI client. Ask it to use the hk tools.';
    root.querySelectorAll('[data-client]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.client === clientKind)));
    $('#mhk-radius').value = String(state.radius);
    $('.mhk-search button').disabled = pending;
    $('.mhk-found').hidden = !selected;
    if (selected) {
      $('[data-dynamic=address]').textContent = label(selected.address);
      const districtName = population ? label(population.data.name) : selected.districtId || 'District unavailable';
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
    $('[data-dynamic=count]').textContent = summary ? `${summary.totalMatched} ${state.lang === 'en' ? 'matching licences · straight-line distance' : '項符合條件的牌照 · 直線距離'}${response.meta.truncated ? ' · ' + response.data.items.length + (state.lang === 'en' ? ' shown' : ' 項已顯示') : ''}` : pending ? 'Loading…' : '';
    if (summary?.spatialCoverage.unlocatedCount) $('[data-dynamic=count]').textContent += ` · ${summary.spatialCoverage.unlocatedCount} unlocated records across the nonspatial filters`;
    const more = $('#mhk-more'); more.hidden = !response?.meta.nextCursor; more.disabled = pending;
    more.textContent = state.lang === 'en' ? 'Load more' : '載入更多';
    $('[data-dynamic=groups]').textContent = (summary?.byLicenceType || []).map(g => `${g.licenceType}: ${g.count}`).join(' · ');
    const warnings = [...(response?.warnings || []), ...(population?.warnings || [])];
    $('#mhk-warnings').hidden = !warnings.length;
    $('#mhk-warnings').textContent = warnings.map(w => `${w.code}: ${w.message}`).join(' · ');
    $('.mhk-pop-value').textContent = population ? population.data.population.toLocaleString(state.lang === 'en' ? 'en-HK' : 'zh-HK') : '—';
    $('[data-dynamic=year]').textContent = population?.data.referencePeriod || '—';
    if (selected && !population && !pending) $('[data-i18n=populationNote]').textContent = state.lang === 'en' ? 'District statistic unavailable for this selected address.' : '此地址所屬地區的統計資料暫時不可用。';
    if (population) $('[data-i18n=populationNote]').textContent = `${translations[state.lang].populationNote} ${population.data.areaKm2} km² · ${population.data.populationDensity.toLocaleString()} persons/km²`;
    root.querySelectorAll('[data-code]').forEach(e => e.setAttribute('aria-pressed', String(e.dataset.code === state.code)));
    let code = `GET ${location.origin}/api/v1/restaurants?${requestQuery || 'lat=…&lon=…&includeSummary=true'}`;
    if (state.code === 'mcp') code = JSON.stringify({tool: 'hk_restaurant_search', arguments: selected ? {lat: selected.latitude, lon: selected.longitude, radiusM: state.radius, includeSummary: true, lang: state.lang === 'en' ? 'en' : 'zh-Hant'} : {}}, null, 2);
    if (state.code === 'json') code = JSON.stringify(response || {state: 'Choose an address candidate first'}, null, 2);
    $('[data-dynamic=code]').textContent = code;
    const provenance = [ ...(response?.provenance || []), ...(population?.provenance || []) ];
    const sourceBox = $('.mhk-code-source'); sourceBox.replaceChildren();
    for (const p of provenance) {
      const line = document.createElement('p');
      const a = document.createElement('a'); a.href = p.sourceUrl; a.textContent = p.attribution; a.rel = 'noreferrer';
      const stamp = document.createElement('span'); stamp.textContent = ` · checked ${p.lastCheckedAt}${p.stale ? ' · STALE' : ''}${p.referencePeriod ? ` · year ${p.referencePeriod}` : ''}`;
      line.append(a, stamp); sourceBox.append(line);
    }
    if (!provenance.length) sourceBox.textContent = translations[state.lang].provenanceLabel;
  }

  async function loadNearby() {
    const token = ++generation;
    if (!selected) return;
    if (selected.latitude == null || selected.longitude == null) { error('This source address has no verified coordinates. Choose another candidate.'); return; }
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
  $('.mhk-search').addEventListener('submit', async e => {
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
  root.querySelectorAll('[data-screen],[data-go]').forEach(b => b.addEventListener('click', () => { state.screen = b.dataset.screen || b.dataset.go; render(); }));
  $('.mhk-language').addEventListener('click', () => { state.lang = state.lang === 'en' ? 'zh' : 'en'; render(); });
  $('#mhk-radius').addEventListener('change', e => { state.radius = Number(e.target.value); loadNearby(); });
  root.querySelectorAll('[data-code]').forEach(b => b.addEventListener('click', () => { state.code = b.dataset.code; render(); }));

  async function status() {
    try {
      const result = await api('/api/v1/status');
      const box = $('#mhk-status'); box.replaceChildren();
      for (const source of result.sources) {
        const item = document.createElement('article');
        const name = document.createElement('h2'); name.textContent = source.sourceId;
        const status = document.createElement('p'); status.textContent = `${source.stale ? 'No recent successful check' : 'Recent successful source check'}${source.recordCount ? ' · ' + source.recordCount.toLocaleString() + ' records' : ''}`;
        const detail = document.createElement('p'); detail.className = 'mhk-small'; detail.textContent = `Last success: ${source.lastSuccess || 'not checked'} · Last error: ${source.lastError || 'none'}`;
        const link = document.createElement('a'); link.href = source.sourceUrl; link.textContent = 'Official dataset ↗'; link.rel = 'noreferrer';
        item.append(name, status, detail, link); box.append(item);
      }
    } catch (e) { $('#mhk-status').textContent = e.message; }
  }
  root.querySelectorAll('[data-client]').forEach(b => b.addEventListener('click', () => { clientKind = b.dataset.client; $('#mhk-copy-status').textContent = ''; render(); }));
  $('#mhk-copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#mhk-install').textContent); $('#mhk-copy-status').textContent = state.lang === 'en' ? ' Copied' : ' 已複製'; } catch { $('#mhk-copy-status').textContent = ' Select and copy the example above.'; } });
  render(); status();
})();
