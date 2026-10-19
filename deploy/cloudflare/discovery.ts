import generatedRoutes from './discovery-routes.json' with {type: 'json'};

const routes: Record<string, Record<string, string>> = generatedRoutes;
export const discoveryFiles = ['/robots.txt', '/sitemap.xml', '/llms.txt'];
export const publicPaths = Object.keys(routes);

export function discoveryTarget(url: URL): {redirect?: string; asset?: string; noindex?: boolean} {
  if (url.pathname === '/data' || (url.pathname.endsWith('/') && url.pathname !== '/' && routes[url.pathname.slice(0, -1)])) {
    const path = url.pathname === '/data' ? '/coverage' : url.pathname.slice(0, -1);
    return {redirect: path + url.search};
  }
  if (discoveryFiles.includes(url.pathname)) return {asset: url.pathname};
  const page = routes[url.pathname];
  if (!page) return {};
  const lang = /^(zh|zh-hant|zh-hk)$/i.test(url.searchParams.get('lang') || '') ? 'zh-Hant' : 'en';
  const filtered = url.pathname === '/coverage' && [...url.searchParams.keys()].some(key => key !== 'lang' && !key.startsWith('utm_'));
  return {asset: page[lang + (filtered ? '-filtered' : '')], noindex: filtered || ['/terms', '/privacy'].includes(url.pathname)};
}
