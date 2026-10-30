/* Shared accepted-source adapters; no name/code joins or collection. */
export function recordSources(read, locale = () => 'en') {
const zh = () => locale() === 'zh-Hant';
const labelName = r => zh() ? (r.chinese_name || r.nameZhHant || r.name1 || r.display_name || r.nameEn) : (r.name1 || r.display_name || r.nameEn || r.chinese_name || r.nameZhHant);
const page = (p, items, meta = {}) => ({ items, version: p.meta.version, nextCursor: p.meta.nextCursor, meta: { ...meta, envelope: p } });
function array(p) { if (!Array.isArray(p?.data?.items) || typeof p?.meta?.version !== 'string')
    throw Error('SOURCE_SCHEMA_CHANGED'); return p.data.items; }
function companyItem(r) { if(typeof r.entity_id==='number'&&!Number.isSafeInteger(r.entity_id))throw Error('SOURCE_IDENTITY_CHANGED'); return { id: String(r.entity_id), title: labelName(r) || String(r.entity_id), subtitle: r.chinese_name && r.chinese_name !== labelName(r) ? r.chinese_name : r.name1 || '', raw: r, identity: r.identifier ? `${r.identifier.namespace}:${r.identifier.value}` : `webb:person:${r.entity_id}` }; }
return {
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
        { id: 'licence-archive', label: 'David Webb / Webb-site', notice: '/api/v1/companies/notice', async read(q, s) { const p = await read('/api/v1/companies', { namespace: 'sfc:ce_reference', value: q.value, groupBy: 'organisation', limit: 20, cursor: s.cursor }, s.signal); const matches = array(p); return page(p, matches.map(r => ({ ...companyItem(r), identity: matches.length === 1 && !p.meta.nextCursor ? 'sfc:ce_reference:' + q.value : null, subtitle: q.value }))); }, detail: async (r) => { const base = '/api/v1/companies/' + encodeURIComponent(r.id); const [record, licences] = await Promise.all([read(base, { version: r.version }), read(base + '/licences', { version: r.version, limit: 20 })]); return Object.assign(record, {licences}); } },
        { id: 'licence-observations', label: 'Securities and Futures Commission', async read(q, s) { const capability = await read('/api/v1/sfc/status', {}, s.signal), c = capability.data; const modes = c?.enabledModes || []; if (!modes.includes('rest') || !modes.includes('browser') || !/^sfc-[a-f0-9]{32}$/.test(c.acceptedVersion || ''))
                throw Error('SOURCE_UNAVAILABLE'); const version = s.version || c.acceptedVersion; const p = await read('/api/v1/sfc/corporations/' + q.value, { version }, s.signal); if (p.meta?.version !== version || p.data?.ce !== q.value)
                throw Error('SOURCE_IDENTITY_CHANGED'); return { version, items: [{ id: q.value, title: labelName(p.data) || q.value, subtitle: q.value, date: p.data.observedAt?.slice(0, 10), raw: p.data, identity: 'sfc:ce_reference:' + q.value }], nextCursor: null, meta: { envelope: p, capability: c } }; }, detail: r => read('/api/v1/sfc/corporations/' + r.id, { version: r.version }) }
    ]
};
}
