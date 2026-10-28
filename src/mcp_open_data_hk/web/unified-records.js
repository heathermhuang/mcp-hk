/* One browsing surface. Each adapter reads accepted data only; no source collection. */
import { RecordFeed, feedRows, feedCheckpoint, readCheckpoint } from './record-feed.js';
import { fetchPublicJson } from './http.js';
import { pagePackage } from './company-export.js';
import {partyNames} from './company-fields.js';
const $ = id => document.getElementById(id), root = document.querySelector('[data-record-kind]');
const kind = root.dataset.recordKind, zh = () => MhkI18n.lang === 'zh';
const common = {
    en: { search: 'Search', results: 'Matching records', previous: 'Previous page', next: 'Next page', retry: 'Retry unavailable records', sources: 'Source coverage, original records and complete downloads', loading: 'Reading records…', initial: 'Search to browse available records across dates.', empty: 'No matching records in the available coverage.', partial: 'Some records could not be read. Available results are shown; retry to include the unavailable records.', failed: 'The records could not be read. Please retry.', count: '{n} records on this page', page: 'Page {n}', selected: 'Selected record', history: 'History and related records', details: 'Source, dates and original fields', source: 'Source', version: 'Dataset version', unknown: 'Unknown', download: 'Download selected records · ZIP', saved: 'Download prepared. SHA-256: ', scope: 'Dated source records; missing entries do not prove absence or current status.', date: 'Record date', identity: 'Source identifier', choose: 'Choose this issuer', names: 'Name history', officers: 'Officers', licences: 'Licences', licence_relationships: 'Licence relationships', addresses: 'Address observations', more: 'Next history page', back: 'Back to selected record', noHistory: 'No records in this history page.', duplicate: 'Multiple source observations of this record', event: 'Event date', summary: 'Summary date', filed: 'Filing date', observed: 'Observed', before: 'Before event', after: 'After event', revision: 'Amendments and revisions', stock: 'Stock code', notice: 'Original attribution notice' },
    'zh-Hant': { search: '搜尋', results: '相符紀錄', previous: '上一頁', next: '下一頁', retry: '重試未能讀取的紀錄', sources: '來源涵蓋範圍、原始紀錄及完整下載', loading: '正在讀取紀錄…', initial: '搜尋各日期可用的紀錄。', empty: '現有涵蓋範圍內沒有相符紀錄。', partial: '部分紀錄未能讀取。下方列出可用結果；請重試以納入未能讀取的紀錄。', failed: '未能讀取紀錄，請重試。', count: '本頁有 {n} 項紀錄', page: '第 {n} 頁', selected: '所選紀錄', history: '歷史及相關紀錄', details: '來源、日期及原始欄位', source: '來源', version: '資料版本', unknown: '未知', download: '下載所選紀錄 · ZIP', saved: '下載已備妥。SHA-256：', scope: '紀錄附有來源日期；沒有紀錄不代表不存在或反映目前狀態。', date: '紀錄日期', identity: '來源識別碼', choose: '選擇此發行人', names: '名稱紀錄', officers: '董事及高級人員', licences: '牌照', licence_relationships: '牌照關係', addresses: '地址觀察', more: '下一頁歷史紀錄', back: '返回所選紀錄', noHistory: '本頁沒有歷史紀錄。', duplicate: '此紀錄的多項來源觀察', event: '事件日期', summary: '摘要日期', filed: '提交日期', observed: '觀察日期', before: '事件前', after: '事件後', revision: '修訂及更正', stock: '股份代號', notice: '原始署名聲明' }
};
const tr = (key, values = {}) => (common[MhkI18n.locale]?.[key] || common.en[key] || key).replace(/\{(\w+)\}/g, (_, k) => values[k] ?? '{' + k + '}');
const node = (tag, value, cls) => { const n = document.createElement(tag); if (value != null)
    n.textContent = String(value); if (cls)
    n.className = cls; return n; };
const button = (label, fn) => { const n = node('button', label, 'mhk-button mhk-secondary'); n.type = 'button'; n.addEventListener('click', fn); return n; };
const labelName = r => zh() ? (r.chinese_name || r.nameZhHant || r.name1 || r.display_name || r.nameEn) : (r.name1 || r.display_name || r.nameEn || r.chinese_name || r.nameZhHant);
const path = (base, query = {}) => base + '?' + new URLSearchParams(Object.entries(query).filter(([, v]) => v != null && v !== ''));
const read = (base, query, signal) => fetchPublicJson(path(base, query), null, { signal });
const page = (p, items, meta = {}) => ({ items, version: p.meta.version, nextCursor: p.meta.nextCursor, meta: { ...meta, envelope: p } });
function array(p) { if (!Array.isArray(p?.data?.items) || typeof p?.meta?.version !== 'string')
    throw Error('SOURCE_SCHEMA_CHANGED'); return p.data.items; }
function companyItem(r) { return { id: String(r.entity_id), title: labelName(r) || String(r.entity_id), subtitle: r.chinese_name && r.chinese_name !== labelName(r) ? r.chinese_name : r.name1 || '', raw: r, identity: r.identifier ? `${r.identifier.namespace}:${r.identifier.value}` : `webb:person:${r.entity_id}` }; }
// Archive search versions travel in signed cursors. RecordFeed independently
// checks returned versions against saved checkpoints; only official search takes version.
const sources = {
    companies: [
        { id: 'company-archive', label: 'David Webb / Webb-site', notice: '/api/v1/companies/notice', async read(q, s) { const p = await read('/api/v1/companies', { q: q.value, groupBy: 'organisation', limit: 20, cursor: s.cursor }, s.signal); return page(p, array(p).map(companyItem)); }, detail: r => read('/api/v1/companies/' + encodeURIComponent(r.id), { version: r.version }) },
        { id: 'company-observations', label: 'Companies Registry / DATA.GOV.HK', notice: null, async read(q, s) { const p = await read('/api/v1/companies', { q: q.value, view: 'latest_observed', groupBy: 'organisation', limit: 20, version: s.version, cursor: s.cursor }, s.signal); return page(p, array(p).map(companyItem)); }, detail: r => read('/api/v1/companies/' + encodeURIComponent(r.id), { view: 'latest_observed', version: r.version }) }
    ],
    hkex: [
        { id: 'disclosure-summary', label: 'HKEX', notice: '/api/v1/hkex/latest/notice', async read(q, s) { const p = await read('/api/v1/hkex/latest/disclosures', { stockCode: q.value, limit: 20, version: s.version, cursor: s.cursor }, s.signal); return page(p, array(p).map(r => ({ id: r.id, title: r.discloser, subtitle: r.stock_code + ' · ' + r.issuer_name, date: r.event_date, raw: r, identity: r.serial ? 'hkex:serial:' + r.serial : null }))); }, detail: r => read('/api/v1/hkex/latest/disclosures/' + encodeURIComponent(r.id), { version: r.version }) },
        { id: 'disclosure-archive', label: 'David Webb / Webb-site', notice: '/api/v1/hkex/archive/notice', async read(q, s) {
                let issuer = q.issuer || s.meta?.issuer, version = s.version || q.issuerVersion;
                if (!issuer) {
                    const p = await read('/api/v1/hkex/archive/issuers', { stockCode: q.value, limit: 20, version, cursor: s.cursor }, s.signal);
                    const matches = array(p);
                    version = p.meta.version;
                    if (matches.length === 1 && !p.meta.nextCursor)
                        issuer = matches[0].issuer_id;
                    else
                        return page(p, matches.map(r => ({ id: r.issuer_id, title: r.name, subtitle: [r.issuer_id, r.first_event, r.last_event].filter(Boolean).join(' · '), issuerChoice: true, raw: r })));
                }
                const p = await read('/api/v1/hkex/archive/disclosures', { issuerId: issuer, limit: 20, version, cursor: q.issuer || s.meta?.issuer ? s.cursor : null }, s.signal);
                return page(p, array(p).map(r => ({ id: r.id, title: [r.discloser.name1, r.discloser.name2, r.discloser.chinese_name].filter(Boolean).join(' / '), subtitle: r.issuer_name || issuer, date: r.event_date, raw: r, identity: r.serial ? 'hkex:serial:' + r.serial : null })), { issuer });
            }, detail: r => read('/api/v1/hkex/archive/disclosures/' + encodeURIComponent(r.id), { version: r.version }) }
    ],
    sfc: [
        { id: 'licence-archive', label: 'David Webb / Webb-site', notice: '/api/v1/companies/notice', async read(q, s) { const p = await read('/api/v1/companies', { namespace: 'sfc:ce_reference', value: q.value, groupBy: 'organisation', limit: 20, cursor: s.cursor }, s.signal); const matches = array(p); return page(p, matches.map(r => ({ ...companyItem(r), identity: matches.length === 1 && !p.meta.nextCursor ? 'sfc:ce_reference:' + q.value : null, subtitle: q.value }))); }, detail: async (r) => { const base = '/api/v1/companies/' + encodeURIComponent(r.id); const [record, licences] = await Promise.all([read(base, { version: r.version }), read(base + '/licences', { version: r.version, limit: 20 })]); return { ...record, licences }; } },
        { id: 'licence-observations', label: 'Securities and Futures Commission', async read(q, s) { const capability = await read('/api/v1/sfc/status', {}, s.signal), c = capability.data; const modes = c?.enabledModes || []; if (!modes.includes('rest') || !modes.includes('browser') || !/^sfc-[a-f0-9]{32}$/.test(c.acceptedVersion || ''))
                throw Error('SOURCE_UNAVAILABLE'); const version = s.version || c.acceptedVersion; const p = await read('/api/v1/sfc/corporations/' + q.value, { version }, s.signal); if (p.meta?.version !== version || p.data?.ce !== q.value)
                throw Error('SOURCE_IDENTITY_CHANGED'); return { version, items: [{ id: q.value, title: labelName(p.data) || q.value, subtitle: q.value, date: p.data.observedAt?.slice(0, 10), raw: p.data, identity: 'sfc:ce_reference:' + q.value }], nextCursor: null, meta: { envelope: p, capability: c } }; }, detail: r => read('/api/v1/sfc/corporations/' + r.id, { version: r.version }) }
    ]
};
const feed = new RecordFeed(sources[kind]);
let query = null, selected = null, detailRun = 0, loading = false, viewRun = 0, pageOffset = 0;
function applyCopy() { document.querySelectorAll('[data-feed-copy][data-i18n]').forEach(e => e.textContent = MhkI18n.t(e.dataset.i18n)); document.title = root.querySelector('h1').textContent + ' · mcp.hk'; $('record-query').placeholder = kind === 'companies' ? (zh() ? '香港、HONG KONG…' : 'HONG KONG, 香港…') : kind === 'hkex' ? '00005' : 'AAB241'; $('record-query').minLength = kind === 'companies' ? 2 : 1; if (kind === 'hkex') {
    $('record-query').pattern = '[0-9]{1,5}';
    $('record-query').inputMode = 'numeric';
    $('record-query').maxLength = 5;
} if (kind === 'sfc') {
    $('record-query').pattern = '[A-Za-z]{3}[0-9]{3}';
    $('record-query').maxLength = 6;
} render(); }
function updateUrl(replace = false) { const u = new URL(location.pathname, location.origin); u.searchParams.set('lang', MhkI18n.locale); if (query) {
    u.searchParams.set('q', query.value);
    if (query.issuer) {
        u.searchParams.set('issuer', query.issuer);
        if (query.issuerVersion)
            u.searchParams.set('issuerVersion', query.issuerVersion);
    }
} if (feed.current) u.searchParams.set('pageState', JSON.stringify(feedCheckpoint(feed.current, pageOffset + feed.index + 1)));
if (selected) {
    u.searchParams.set('record', selected.key);
    u.searchParams.set('recordVersion', selected.version);
} history[replace ? 'replaceState' : 'pushState'](null, '', u.pathname + u.search); }
function render() { const current = feed.current, rows = feedRows(current, MhkI18n.locale), states = Object.values(current?.states || {}), failed = states.some(s => s.error); $('record-status').textContent = loading ? tr('loading') : failed ? (rows.length ? tr('partial') : tr('failed')) : current ? rows.length ? tr('count', { n: rows.length }) : tr('empty') : tr('initial'); const credits=sources[kind].filter(source=>current?.states[source.id]?.items.length).map(source=>source.label);$('record-attribution').textContent=credits.length?(zh()?'資料來源：':'Data: ')+credits.join(' · '):''; $('record-search').querySelector('button').disabled = loading; $('record-results').replaceChildren(); for (const r of rows) {
    const a = node('article', null, 'mhk-record-row'), b = button(r.title, () => open(r));
    b.className = 'mhk-record-title';
    b.setAttribute('aria-pressed', String(selected?.key === r.key));
    a.append(b);
    if (r.subtitle && r.subtitle !== r.title)
        a.append(node('p', r.subtitle));
    if (r.date)
        a.append(node('p', tr(kind === 'hkex' ? 'event' : 'date') + ': ' + r.date));
    if (r.issuerChoice)
        a.append(node('p', tr('choose')));
    $('record-results').append(a);
} for (const id of ['record-next', 'record-previous', 'record-retry'])
    $(id).disabled = loading; $('record-next').hidden = !feed.hasNext; $('record-previous').hidden = feed.index + pageOffset < 1; $('record-retry').hidden = !failed; $('record-page').textContent = current ? tr('page', { n: pageOffset + feed.index + 1 }) : ''; }
async function search(value, {restore = false, issuer = null, issuerVersion = null, checkpoint = null} = {}) {
    const run = ++viewRun;
    detailRun++; selected = null; $('record-detail').hidden = true;
    query = {value: kind === 'hkex' ? value.padStart(5, '0') : kind === 'sfc' ? value.toUpperCase() : value, issuer, issuerVersion};
    loading = true; pageOffset = checkpoint ? checkpoint.number - 1 : 0;
    feed.cancel(); feed.pages = []; feed.index = -1;
    render(); if (!restore) updateUrl();
    if (checkpoint) {feed.query = query; await feed.load(checkpoint.sources);}
    else await feed.search(query);
    if (run !== viewRun) return false;
    loading = false; render(); if (!restore) updateUrl(true);
    return true;
}
function facts(target, items) { const dl = node('dl', null, 'mhk-record-facts'); for (const [key, value] of items) {
    if (value == null || value === '')
        continue;
    dl.append(node('dt', key), node('dd', typeof value === 'object' ? JSON.stringify(value) : value));
} target.append(dl); }
function disclosedDate(raw, precision) { return raw == null ? tr('unknown') : String(raw) + (precision ? ' · ' + precision : ''); }
function companyFacts(target, d) { facts(target, [[MhkI18n.t('companyInc'), disclosedDate(d.inc_raw, d.inc_precision)], [MhkI18n.t('companyDissolved'), disclosedDate(d.dissolved_raw, d.dissolved_precision)], ...(d.identifiers || []).map(i => [i.namespace, i.value])].filter(([, v]) => v !== tr('unknown'))); if (d.identifier)
    facts(target, [[d.identifier.namespace, d.identifier.value]]); if (d.latestAddress)
    facts(target, [[tr('addresses'), d.latestAddress.address], [tr('observed'), d.latestAddress.observedAt]]); for (const obs of d.observations || []) {
    const a = node('article', null, 'mhk-record-observation');
    facts(a, [[tr('date'), obs.coverageEnd || obs.observedAt || obs.source?.fetchedAt], [tr('names'), obs.names?.join(' / ') || obs.name1], [tr('addresses'), obs.address], ...((obs.events || []).map(e => [e.type, disclosedDate(e.dateRaw, e.precision)])), [tr('licences'), obs.raw?.ML_Lic_No], [MhkI18n.t('companyFactDates'), obs.licenceExpiry?.dateRaw]]);
    target.append(a);
} }
function licenceFacts(target, d) { facts(target, [[tr('identity'), d.ce], [tr('observed'), d.observedAt], [MhkI18n.t('sfcLiveSourceCutoff'), disclosedDate(d.sourceCutoff?.raw, d.sourceCutoff?.precision)], [MhkI18n.t('hkexState'), d.statusLabel]]); for (const a of d.activities || []) {
    const box = node('article', null, 'mhk-record-observation');
    box.append(node('h3', a.label));
    facts(box, [[MhkI18n.t('hkexState'), a.statusLabel], [MhkI18n.t('sfcArchiveStart'), disclosedDate(a.start?.raw, a.start?.precision)], [MhkI18n.t('sfcArchiveEnd'), disclosedDate(a.end?.raw, a.end?.precision)]]);
    target.append(box);
} }
function disclosureFacts(target, d, variant) { facts(target, [[tr('identity'), d.serial || d.id], [tr('stock'), d.stock_code], [MhkI18n.t('dailyIssuer'), d.issuer_name || d.issuer_id], [tr('event'), disclosedDate(d.event_date)], [tr('summary'), disclosedDate(d.summary_date)], [tr('filed'), disclosedDate(d.filed_date)], [MhkI18n.t('webbAware'), d.awareness_date], [MhkI18n.t('webbSigned'), d.signed_date], [MhkI18n.t('dailyForm'), d.form || d.form_label || d.form_code], [MhkI18n.t('dailyInvolved'), d.shares_involved_as_disclosed], [MhkI18n.t('dailyPrice'), d.average_price_as_disclosed], [MhkI18n.t('dailyCurrency'), d.currency_as_disclosed]]); for (const phase of ['before', 'after']) {
    const b = node('section');
    b.append(node('h3', tr(phase)));
    if (d[phase]) facts(b, [['long_shares','hkexLong','hkexShares'],['long_percent','hkexLong','hkexPercent'],['short_shares','hkexShort','hkexShares'],['short_percent','hkexShort','hkexPercent']].map(([field,position,unit])=>[MhkI18n.t(position)+' · '+MhkI18n.t(unit),d[phase][field]??tr('unknown')]));
    for (const line of (d.interests || []).filter(x => x.phase === phase))
        facts(b, [[MhkI18n.t({ long: 'hkexLong', short: 'hkexShort', lending_pool: 'hkexLending' }[line.position] || 'hkexUnknown'), line.shares], [MhkI18n.t('hkexPercent'), line.percentage]]);
    target.append(b);
} for (const line of [...(d.capacities || []), ...(d.events || [])])
    facts(target, [[MhkI18n.t('webbReason'), line.reason_label || line.capacity_label || line.reason || line.capacity_code], [MhkI18n.t('hkexShares'), line.shares ?? line.shsInv]]); for (const edge of d.revision_links || []) {
    const b = node('p', `${tr('revision')}: ${edge.relation} · ${edge.serial}`);
    target.append(b);
    if (edge.resolved && edge.filing_id)
        target.append(button(edge.serial, () => open({ ...variant, id: edge.filing_id, key: variant.source + ':' + edge.filing_id, variants: null })));
} if (d.revision?.remarks)
    target.append(node('p', d.revision.remarks)); }
function historyRows(target, items) { target.replaceChildren(); if (!items.length)
    target.append(node('p', tr('noHistory'))); for (const item of items) {
    const a = node('article', null, 'mhk-record-observation');
    if (item.observedAt)
        a.append(node('p', tr('observed') + ': ' + item.observedAt));
    else {const names=partyNames(item.party,MhkI18n.lang),title=item.display_name||names.primary||item.activity_label;if(title)a.append(node('h3',title));if(names.secondary)a.append(node('p',names.secondary));}
    facts(a, [[tr('addresses'), item.address], [MhkI18n.t('companyFactRole'), item.role_label ?? item.role_code], [MhkI18n.t('sfcArchiveActivity'), item.activity_label], [MhkI18n.t('sfcArchiveStart'), item.start_raw == null ? null : disclosedDate(item.start_raw, item.start_precision)], [MhkI18n.t('sfcArchiveEnd'), item.end_raw == null ? null : disclosedDate(item.end_raw, item.end_precision)], [MhkI18n.t('companyFormer'), item.until_raw == null ? null : disclosedDate(item.until_raw, item.until_precision)]]);
    const full = node('details');
    full.append(node('summary', tr('details')), node('pre', JSON.stringify(item, null, 2)));
    a.append(full);
    target.append(a);
} }
async function open(row, { restore = false } = {}) {
    if (row.issuerChoice) {
        await search(query.value, { issuer: row.id, issuerVersion: row.version });
        return;
    }
    const run = ++detailRun;
    selected = row;
    if (!restore)
        updateUrl();
    render();
    $('record-detail').hidden = false;
    $('record-detail-heading').textContent = row.title;
    $('record-content').replaceChildren(node('p', tr('loading')));
    const variants = row.variants || [row];
    const results = await Promise.allSettled(variants.map(r => sources[kind].find(s => s.id === r.source).detail(r)));
    if (run !== detailRun)
        return;
    const box = $('record-content');
    box.replaceChildren();
    for (let i = 0; i < variants.length; i++) {
        const variant = variants[i], source = sources[kind].find(s => s.id === variant.source), result = results[i];
        if (result.status !== 'fulfilled') {
            box.append(node('p', tr('failed')));
            continue;
        }
        const p = result.value, d = p.data;
        if (p.meta?.version !== variant.version || !d || String(d.entity_id ?? d.ce ?? d.id) !== variant.id) {
            box.append(node('p', tr('failed')));
            continue;
        }
        if(i===0)$('record-detail-heading').textContent=kind==='hkex'?(typeof d.discloser==='string'?d.discloser:[d.discloser?.name1,d.discloser?.name2,d.discloser?.chinese_name].filter(Boolean).join(' / '))||row.title:labelName(d)||row.title;
        const section = node('section', null, 'mhk-record-variant');
        if (variants.length > 1)
            section.append(node('h3', labelName(d) || row.title));
        section.append(node('p', tr('scope'), 'mhk-note'));
        if (kind === 'companies' || variant.source === 'licence-archive')
            companyFacts(section, d);
        else if (kind === 'sfc')
            licenceFacts(section, d);
        else
            disclosureFacts(section, d, variant);
        const related = node('div');
        section.append(related);
        let family = null, cursor = null;
        const families = kind === 'companies' ? (variant.source === 'company-archive' ? ['names', 'officers', 'licences', 'licence_relationships'] : ['addresses']) : kind === 'sfc' ? (variant.source === 'licence-archive' ? ['licences', 'licence_relationships'] : feed.current?.states[variant.source]?.meta?.capability?.historyAvailable ? ['history'] : []) : [];
        if (families.length) {
            const nav = node('nav', null, 'mhk-record-actions');
            nav.setAttribute('aria-label', tr('history'));
            for (const key of families)
                nav.append(button(tr(key), () => { family = key; cursor = null; loadHistory(); }));
            section.append(nav);
        }
        const listing = node('div'), more = button(tr('more'), () => loadHistory());
        more.hidden = true;
        related.append(listing, more);
        let historyRun = 0;
        async function loadHistory() { const turn = ++historyRun, chosen = family, current = cursor; more.disabled = true; listing.textContent = tr('loading'); try {
            const base = variant.source === 'licence-observations' ? '/api/v1/sfc/corporations/' : '/api/v1/companies/';
            const response = await read(base + encodeURIComponent(variant.id) + '/' + chosen, { version: variant.version, limit: 20, cursor: current, view: variant.source === 'company-observations' ? 'latest_observed' : undefined });
            if (run !== detailRun || turn !== historyRun)
                return;
            if (response.meta?.version !== variant.version)
                throw Error('VERSION_CHANGED');
            const items = Array.isArray(response.data) ? response.data : array(response);
            historyRows(listing, items);
            if (chosen === 'history')
                for (const item of items) {
                    const a = node('a', item.observedAt || item.version);
                    a.href = path('/sfc', { q: variant.id, record: variant.source + ':' + variant.id, recordVersion: item.version, lang: MhkI18n.locale });
                    listing.append(a);
                }
            cursor = response.meta.nextCursor || null;
            more.hidden = !cursor;
        }
        catch {
            if (run === detailRun && turn === historyRun)
                listing.textContent = tr('failed');
        }
        finally {
            if (turn === historyRun)
                more.disabled = false;
        } }
        if (p.licences) {
            historyRows(listing, array(p.licences));
            if (p.licences.meta.nextCursor) {
                family = 'licences';
                cursor = p.licences.meta.nextCursor;
                more.hidden = false;
            }
        }
        const provenance = node('details');
        provenance.append(node('summary', tr('details')));
        facts(provenance, [[tr('source'), source.label], [tr('version'), p.meta.version], [tr('identity'), variant.id]]);
        if (d.source_url) {
            const url = new URL(d.source_url, location.origin);
            if (['https:', 'http:'].includes(url.protocol)) {
                const a = node('a', tr('source'));
                a.href = url.href;
                a.rel = 'noreferrer';
                provenance.append(a);
            }
        }
        provenance.append(node('pre', JSON.stringify(p, null, 2)));
        section.append(provenance);
        if (source.notice || variant.source === 'company-observations') {
            const receipt = node('p', null, 'mhk-note');
            const download = button(tr('download'), async () => { download.disabled = true; try {
                const notice = source.notice ? await fetch(source.notice).then(r => { if (!r.ok)
                    throw Error('NOTICE_UNAVAILABLE'); return r.text(); }) : 'Government of the HKSAR / Companies Registry / DATA.GOV.HK.\nhttps://data.gov.hk/en/terms-and-conditions';
                const pack = await pagePackage({ meta: p.meta, provenance: p.provenance, warnings: p.warnings, data: { items: [d] } }, { family: 'selected-record', entityId: variant.id }, notice);
                if (run !== detailRun)
                    return;
                const a = node('a'), url = URL.createObjectURL(pack.blob);
                a.href = url;
                a.download = pack.filename;
                a.click();
                setTimeout(() => URL.revokeObjectURL(url), 5000);
                receipt.textContent = tr('saved') + pack.sha256;
            }
            catch {
                if (run === detailRun)
                    receipt.textContent = tr('failed');
            }
            finally {
                download.disabled = false;
            } });
            section.append(download, receipt);
        }
        else if (p.meta.export?.url === '/api/v1/sfc/exports/' + variant.version + '.zip') {
            const a = node('a', MhkI18n.t('sfcExportDownload'), 'mhk-button mhk-secondary');
            a.href = p.meta.export.url;
            a.download = variant.version + '.zip';
            section.append(node('p', MhkI18n.t('sfcExportScope')), a);
        }
        box.append(section);
    }
    $('record-detail-heading').focus({ preventScroll: true });
}
async function restore() { const p = new URLSearchParams(location.search); if (legacyLink(p))
    return; const value = p.get('q') || (kind === 'sfc' ? p.get('ce') : null); if (value) {
    $('record-query').value = value;
    const checkpoint = readCheckpoint(p.get('pageState'), sources[kind].map(s=>s.id));
    if (!await search(value, {restore:true, issuer:p.get('issuer'), issuerVersion:p.get('issuerVersion'), checkpoint})) return;
    const key = p.get('record'), version = p.get('recordVersion'), r = feedRows(feed.current, MhkI18n.locale).find(r => r.key === key);
    if (r) {
        if (version && version !== r.version) {
            r.version = version;
            r.variants = null;
        }
        await open(r, { restore: true });
    }
    else if (key && version) {
        const source = sources[kind].find(s => key.startsWith(s.id + ':'));
        if (source)
            await open({ id: key.slice(source.id.length + 1), key, source: source.id, version, title: tr('selected') }, { restore: true });
    }
}
else {
    viewRun++;pageOffset=0;feed.cancel();
    feed.pages = [];
    feed.index = -1;
    selected = null;
    query = null;
    detailRun++;
    $('record-query').value = '';
    $('record-detail').hidden = true;
    render();
} }
$('record-search').addEventListener('submit', e => { e.preventDefault(); search($('record-query').value.trim()); });
$('record-next').addEventListener('click', async () => { loading = true; render(); await feed.next(); loading = false; selected = null; detailRun++; $('record-detail').hidden = true; updateUrl(true); render(); });
$('record-previous').addEventListener('click', () => { if(feed.index===0&&pageOffset){search(query.value,{issuer:query.issuer,issuerVersion:query.issuerVersion});return;}feed.previous(); selected = null; detailRun++; $('record-detail').hidden = true; updateUrl(true); render(); });
$('record-retry').addEventListener('click', async () => { loading = true; render(); await feed.retry(); loading = false; updateUrl(true); render(); });
window.addEventListener('mhk:language', () => { applyCopy(); restore(); });
window.addEventListener('popstate', restore);
function legacyLink(p) { return p.has('entity') || p.has('namespace') || p.has('official_entity') || p.has('companySource') || p.get('view') === 'sfc_observation'; }
let legacyLoaded = false;
$('record-sources').addEventListener('toggle', async () => { if (!$('record-sources').open || legacyLoaded)
    return; legacyLoaded = true; for (const file of { companies: ['companies.js'], hkex: ['hkex.js', 'webb-sdi.js', 'hkex-latest.js'], sfc: ['sfc.js'] }[kind])
    await import('./' + file); $('record-sources').dataset.ready = 'true'; });
// Original bookmarked source-identifier/detail URLs remain available in the full explorer.
const initial = new URLSearchParams(location.search);
if (legacyLink(initial))
    $('record-sources').open = true;
applyCopy();
restore();
