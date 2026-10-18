import {fetchPublicJson} from './http.js';

const $ = id => document.getElementById(id), t = (key, values) => MhkI18n.t(key, values);
const node = (tag, text) => { const e = document.createElement(tag); e.textContent = text; return e; };
let sequence = 0, candidates = [], buildingId = null, result = null, kind = null;
function show() {
  $('property-candidates').replaceChildren();
  for (const candidate of candidates) {
    const button = node('button', `${candidate.name || candidate.id} · ${candidate.district || ''}`);
    button.type = 'button'; button.className = 'mhk-button mhk-secondary';
    button.addEventListener('click', () => { buildingId = candidate.id; read('building', {buildingId}); });
    $('property-candidates').append(button);
  }
  $('property-records').replaceChildren();
  $('property-building').hidden = !result || !['building', 'price-history'].includes(kind);
  if (!result) return;
  const d = result.data;
  if (kind === 'building') {
    $('property-building-name').textContent = d.name || d.id;
    $('property-building-state').textContent = `${t('propertyReturned', {count:d.listings.length})} · ${d.listingState.message || ''} · ${d.stats.lastUpdated || '—'}`;
    for (const listing of d.listings) {
      const row = node('article', ''); row.className = 'mhk-pack';
      row.append(node('h3', listing.title || listing.id));
      const price = listing.priceHkd == null ? '—' : `HK$${listing.priceHkd.toLocaleString(MhkI18n.locale)}`;
      row.append(node('p', `${t(listing.mode === 'rent' ? 'propertyRent' : 'propertyBuy')} · ${price} · ${listing.saleableAreaFt2 ?? '—'} ft²`));
      row.append(node('p', `${listing.source} · ${{fresh:t('propertyFresh'),recent:t('propertyRecent'),stale:t('propertyStale')}[listing.freshness.status] || listing.freshness.status} · ${listing.freshness.observedAt || listing.updatedAt || '—'}`));
      const url = new URL(listing.sourceUrl);
      if (url.protocol === 'https:' && !url.username && !url.password) { const a = node('a', t('propertySource')); a.href = url.href; a.rel = 'noreferrer'; row.append(a); }
      $('property-records').append(row);
    }
    if (!d.listings.length) $('property-records').append(node('p', t('propertyEmpty')));
  } else if (kind === 'price-history') {
    $('property-building-name').textContent = t('propertyHistory');
    $('property-building-state').textContent = `${d.buildingId} · ${d.generatedAt}`;
    for (const event of d.events) $('property-records').append(node('p', `${event.observedAt} · ${event.source}:${event.sourceListingId} · ${event.mode === 'buy' ? t('propertyBuy') : event.mode === 'rent' ? t('propertyRent') : '—'} · HK$${event.oldPriceHkd ?? '—'} → HK$${event.newPriceHkd ?? '—'}`));
    if (!d.events.length) $('property-records').append(node('p', t('propertyEmpty')));
  }
  $('property-response').hidden = false;
  $('property-response').open = kind === 'coverage';
  $('property-json').textContent = JSON.stringify(result, null, 2);
}
async function read(operation, params = {}) {
  const token = ++sequence; kind = operation; result = null;
  $('property-status').textContent = t('propertyLoading');
  $('property-response').hidden = true;
  if (operation === 'search') { candidates = []; buildingId = null; }
  show();
  const args = operation === 'coverage' ? {} : {...params, lang:MhkI18n.locale};
  const path = '/api/v1/properties/' + operation + (Object.keys(args).length ? '?' + new URLSearchParams(args) : '');
  $('property-code').textContent = `GET ${path}\n\nMCP: ${{search:'hk_property_search',building:'hk_property_building','price-history':'hk_property_price_history',coverage:'hk_property_coverage'}[operation]}(${JSON.stringify(args)})`;
  try {
    const response = await fetchPublicJson(path);
    if (token !== sequence) return;
    result = response;
    if (operation === 'search') candidates = result.data.candidates;
    $('property-status').textContent = operation === 'search' && !candidates.length ? t('propertyEmpty') : '';
    show();
  } catch (error) { if (token === sequence) $('property-status').textContent = error.message; }
}
$('property-search').addEventListener('submit', event => { event.preventDefault(); if ($('property-query').value.trim()) read('search', {q:$('property-query').value.trim()}); });
$('property-listings').addEventListener('click', () => { if (buildingId) read('building', {buildingId}); });
$('property-history').addEventListener('click', () => { if (buildingId) read('price-history', {buildingId}); });
$('property-coverage').addEventListener('click', () => read('coverage'));
window.addEventListener('mhk:language', () => {
  if (kind === 'search') read('search', {q:$('property-query').value.trim()});
  else if (buildingId && ['building', 'price-history'].includes(kind)) read(kind, {buildingId});
  else show();
});
