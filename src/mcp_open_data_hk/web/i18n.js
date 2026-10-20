/* Shared locale for every public page. Source data and API identifiers stay verbatim. */
(() => {
  const normalize = value => /^(zh|zh-hant|zh-hk)$/i.test(value || '') ? 'zh' : value === 'en' ? 'en' : null;
  let stored;
  try { stored = localStorage.getItem('mhk-language'); } catch { /* URL locale works without storage. */ }
  const serverRendered = document.documentElement.dataset?.discovery === 'true';
  const requested = normalize(new URL(location.href).searchParams.get('lang'));
  const preferred = normalize(stored);
  let lang = requested || (serverRendered ? normalize(document.documentElement.lang) : preferred) || 'en';
  if (serverRendered && !requested && preferred && preferred !== lang) {
    const url = new URL(location.href); url.searchParams.set('lang', preferred === 'en' ? 'en' : 'zh-Hant');
    location.replace(url.pathname + url.search + url.hash); return;
  }
  const t = (key, values = {}) => {
    const text = translations[lang][key] ?? translations.en[key] ?? key;
    return text.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
  };
  function apply() {
    document.documentElement.lang = lang === 'en' ? 'en' : 'zh-Hant';
    document.querySelectorAll('.mhk-navbutton').forEach(link => {
      const path = new URL(link.getAttribute('href'), location.href).pathname;
      if (path === location.pathname || (path === '/coverage' && ['/data','/plates','/properties','/demo'].includes(location.pathname))) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
    // Only checked-in application headings use translated markup.
    document.querySelectorAll('[data-i18n-html]').forEach(e => { e.innerHTML = t(e.dataset.i18nHtml); });
    for (const attr of ['placeholder', 'aria-label', 'content']) {
      document.querySelectorAll('[data-i18n-' + attr + ']').forEach(e => e.setAttribute(attr, t(e.getAttribute('data-i18n-' + attr))));
    }
    document.querySelectorAll('[data-language-value]').forEach(e=>e.value=lang==='en'?'en':'zh-Hant');
    document.querySelectorAll('.mhk-language').forEach(e => {
      e.textContent = lang === 'en' ? '繁' : 'EN';
      e.setAttribute('aria-label', lang === 'en' ? '切換至繁體中文' : 'Switch to English');
    });
    document.querySelectorAll('a[href]').forEach(e => {
      if (e.getAttribute('href').startsWith('#')) return;
      const url = new URL(e.getAttribute('href'), location.href);
      // The canonical locale link is a no-JS fallback. With JS, the single
      // language button preserves the current same-origin discovery state.
      if (e.hasAttribute?.('hreflang')) { e.hidden = true; return; }
      if (url.origin === location.origin && (['/', '/demo', '/connect', '/sources', '/plates', '/properties', '/coverage', '/data', '/terms', '/privacy', '/about', '/guides'].includes(url.pathname) || url.pathname.startsWith('/guides/'))) {
        url.searchParams.set('lang', lang === 'en' ? 'en' : 'zh-Hant');
        e.setAttribute('href', url.pathname + url.search + url.hash);
      }
    });
  }
  function setLanguage(value) {
    const next = normalize(value); if (!next) return;
    lang = next;
    try { localStorage.setItem('mhk-language', lang); } catch { /* Keep working without storage. */ }
    const url = new URL(location.href); url.searchParams.set('lang', lang === 'en' ? 'en' : 'zh-Hant');
    if (serverRendered) { location.assign(url.pathname + url.search + url.hash); return; }
    history.replaceState(null, '', url.pathname + url.search + url.hash);
    apply(); window.dispatchEvent(new Event('mhk:language'));
  }
  function coverageSummary(box, coverage, failed = false) {
    box.replaceChildren();
    if (!coverage) { box.textContent = t(failed ? 'coverageUnavailable' : 'loadingCoverage'); return; }
    const counts = document.createElement('div'); counts.className = 'mhk-coverage-counts';
    for (const [value, key] of [[coverage.datasets.discovered, 'datasetEntries'], [coverage.resources.discovered, 'resourceEntries'], [coverage.resources.byStatus.queryable || 0, 'queryableResources']]) {
      const item = document.createElement('p'), number = document.createElement('strong'), label = document.createElement('span');
      number.textContent = value.toLocaleString(lang === 'en' ? 'en-HK' : 'zh-HK'); label.textContent = t(key); item.append(number, label); counts.append(item);
    }
    const note = document.createElement('p'); note.className = 'mhk-note'; note.textContent = t('coverageClaim'); box.append(counts, note);
    if (coverage.validationFreshness?.status === 'active') { const p=document.createElement('p');p.className='mhk-note';p.textContent=t('validationCounts',{expired:coverage.validationFreshness.cacheExpiredCount,due:coverage.validationFreshness.reviewOverdueCount});box.append(p); }
    if (coverage.asOf) {
      const stamp = document.createElement('p'); stamp.className = 'mhk-small';
      stamp.textContent = t('coverageAsOf') + ' · ' + new Date(coverage.asOf).toLocaleString(lang === 'en' ? 'en-HK' : 'zh-HK', {timeZone: 'Asia/Hong_Kong', year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) + ' (HKT)'; box.append(stamp);
    }
  }
  window.MhkI18n = {get lang() {return lang;}, get locale() {return lang === 'en' ? 'en' : 'zh-Hant';}, t, apply, setLanguage, coverageSummary};
  document.querySelectorAll('.mhk-language').forEach(button => button.addEventListener('click', () => setLanguage(lang === 'en' ? 'zh' : 'en')));
  window.addEventListener('popstate', () => { const value = normalize(new URL(location.href).searchParams.get('lang')); if (value && value !== lang) { lang = value; apply(); window.dispatchEvent(new Event('mhk:language')); } });
  apply();
})();
