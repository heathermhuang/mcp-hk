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
    question: '“Find licensed restaurants near this address.”',
    navPlates: 'Plate.hk', packsCount: 'Three government packs + one independent provider',
    externalBadge: '04 / FIRST EXTERNAL PACK · PLATE.HK', plateTitle: 'A plate. Its auction history.',
    plateDesc: 'Search historical auction records and source-linked comparisons from Plate.hk, an independent Hong Kong data provider.',
    tryPlate: 'Explore Plate.hk ↗', plateQueryLabel: 'HONG KONG REGISTRATION MARK',
    plateHistory: 'Auction history', plateCompare: 'Historical comparisons',
    plateCollection: 'Collection', plateMatch: 'History match', plateExact: 'Exact', plateContains: 'Contains', plateNext: 'Next page',
    plateCaveat: 'Historical auction amounts are not current valuations, asking prices, ownership or availability. Plate.hk is independent; verify records with their original sources. Comparisons use their own cohort method, rather than the history filters.'
  });
  Object.assign(translations.zh, {
    sample: '查詢示例', illustrative: '官方來源 · 清楚標示出處', sampleBadge: '公共來源資料',
    searchLabel: '查詢香港地址', fixtureNote: '請選擇傳回的地址，再搜尋附近食肆。地址服務並非完整地址名冊。',
    districtAddress: '已選來源地址', populationLabel: '地區人口',
    populationNote: '已發表的全區人口，並非搜尋範圍內的人口。',
    connectionNote: '本實例的連接網址。支援 Streamable HTTP，亦可在本機使用 stdio。',
    previewFooter: '開源開發版本', endpointLabel: '本實例的 MCP 端點', provenanceLabel: '回應資料來源',
    navPlates: 'Plate.hk', packsCount: '三個政府數據包 + 一個獨立供應商',
    externalBadge: '04 / 首個外部數據包 · PLATE.HK', plateTitle: '一個車牌，歷年拍賣紀錄。',
    plateDesc: '透過香港獨立數據供應商 Plate.hk，查詢歷年拍賣紀錄及附原始來源的歷史比較。',
    tryPlate: '探索 Plate.hk ↗', plateQueryLabel: '香港車輛登記號碼',
    plateHistory: '拍賣紀錄', plateCompare: '歷史比較', plateCollection: '資料集',
    plateMatch: '紀錄比對方式', plateExact: '完全符合', plateContains: '包含', plateNext: '下一頁',
    plateCaveat: '歷史拍賣金額並非現時估值、叫價、擁有權或可用狀態。Plate.hk 為獨立供應商，請核對紀錄所附原始來源。歷史比較使用其比較群組方法，不套用拍賣紀錄篩選。'
  });
  let state = {screen: location.pathname === '/plates' ? 'plates' : location.pathname === '/sources' ? 'sources' : location.pathname === '/demo' ? 'explore' : location.pathname === '/connect' ? 'connect' : 'home', lang: 'en', radius: 500, code: 'http'};
  let clientKind = 'codex';
  let selected = null, response = null, population = null, requestQuery = '', pending = false;
  let generation = 0;
  let plateResult = null, platePending = false, plateError = '', plateRequest = null;
  let plateGeneration = 0;
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
      summary.textContent = data.method ? `${data.sampleSize ?? '—'} ${state.lang === 'en' ? 'comparable plates' : '個歷史比較車牌'} · ${data.dateFrom || '—'} → ${data.dateTo || '—'}` : `${data.total} ${state.lang === 'en' ? 'historical records' : '項歷史紀錄'} · ${data.query}`;
      box.append(summary);
      if (data.method) {
        const method = document.createElement('p'); method.className = 'mhk-note'; method.textContent = data.method; box.append(method);
        const stats = document.createElement('p');
        stats.textContent = data.statistics ? `Historical HKD · P25 ${data.statistics.p25.toLocaleString()} · Median ${data.statistics.median.toLocaleString()} · P75 ${data.statistics.p75.toLocaleString()}` : (state.lang === 'en' ? 'No qualified historical price distribution.' : '沒有符合條件的歷史價格分佈。');
        box.append(stats);
      }
      for (const record of data.items) {
        const row = document.createElement('article'); row.className = 'mhk-plate-record';
        const mark = document.createElement('strong');
        mark.textContent = Array.isArray(record.double_line) ? record.double_line.join('\n') : record.double_line || record.single_line;
        const context = document.createElement('p');
        const dateLabel = record.auction_date_label || (record.date_precision === 'year_range' ? record.year_range : record.auction_date) || '—';
        context.textContent = `${dateLabel} · ${record.dataset_key}${record.result_status ? ' · ' + record.result_status : ''}`;
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
        const empty = document.createElement('p'); empty.textContent = state.lang === 'en' ? 'No historical records matched. This does not establish availability.' : '未有符合的歷史紀錄，並不代表此車牌可供申請。'; box.append(empty);
      }
    }
    const more = $('#mhk-plate-more'); more.hidden = !data?.nextPage; more.disabled = platePending;
    if (plateRequest) {
      const {kind, params} = plateRequest;
      $('#mhk-plate-code').textContent = `GET ${location.origin}/api/v1/plates/${kind}?${new URLSearchParams(params)}\n\nMCP: ${kind === 'search' ? 'hk_plate_search' : 'hk_plate_comparables'}(${JSON.stringify(params, null, 2)})`;
    }
    const p = plateResult?.provenance[0];
    $('#mhk-plate-source').textContent = p ? `${p.attribution} · checked ${p.lastCheckedAt} · 5-minute response cache` : '';
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
        const name = document.createElement('h2'); name.textContent = `${source.sourceId} · ${source.providerType === 'independent' ? 'Independent provider' : 'Government source'}`;
        const status = document.createElement('p'); status.textContent = `${source.stale ? 'No recent successful check' : 'Recent successful source check'}${source.recordCount ? ' · ' + source.recordCount.toLocaleString() + ' records' : ''}`;
        const detail = document.createElement('p'); detail.className = 'mhk-small'; detail.textContent = `Last success: ${source.lastSuccess || 'not checked'} · Last error: ${source.lastError || 'none'}`;
        const link = document.createElement('a'); link.href = source.sourceUrl; link.textContent = source.providerType === 'independent' ? 'Provider data & attribution ↗' : 'Official dataset ↗'; link.rel = 'noreferrer';
        item.append(name, status, detail, link); box.append(item);
      }
    } catch (e) { $('#mhk-status').textContent = e.message; }
  }
  root.querySelectorAll('[data-client]').forEach(b => b.addEventListener('click', () => { clientKind = b.dataset.client; $('#mhk-copy-status').textContent = ''; render(); }));
  $('#mhk-copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText($('#mhk-install').textContent); $('#mhk-copy-status').textContent = state.lang === 'en' ? ' Copied' : ' 已複製'; } catch { $('#mhk-copy-status').textContent = ' Select and copy the example above.'; } });
  render(); status();
})();
