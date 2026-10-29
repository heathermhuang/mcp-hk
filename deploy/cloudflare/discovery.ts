import generatedRoutes from './discovery-routes.json' with {type: 'json'};
import agentRoutes from './agent-routes.json' with {type: 'json'};

const routes: Record<string, Record<string, string>> = generatedRoutes;
export const discoveryFiles = ['/robots.txt', '/sitemap.xml', '/llms.txt'];
export const publicPaths = Object.keys(routes);
export const agentFiles: Record<string,{asset:string;contentType:string}> = agentRoutes;
export const discoveryLinks = '<https://mcp.hk/.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json", <https://mcp.hk/openapi.json>; rel="service-desc"; type="application/json", <https://mcp.hk/guides>; rel="service-doc"; type="text/html", <https://mcp.hk/.well-known/mcp/server-card.json>; rel="describedby"; type="application/json", <https://mcp.hk/llms.txt>; rel="describedby"; type="text/plain"';

export function prefersMarkdown(accept: string): boolean {
  const ranges = accept.toLowerCase().split(',').map(part => {
    const [name,...params] = part.split(';').map(value=>value.trim());
    const quality=params.find(value=>value.startsWith('q='));
    const parsed=quality ? Number(quality.slice(2)) : 1;
    return {name,q:Number.isFinite(parsed) && parsed>=0 && parsed<=1 ? parsed : 0};
  });
  const effective=(media:string)=>{
    for (const name of [media,'text/*','*/*']) {
      const matches=ranges.filter(range=>range.name===name);
      if (matches.length) return Math.max(...matches.map(range=>range.q));
    }
    return 0;
  };
  return ranges.some(range=>range.name==='text/markdown') && effective('text/markdown')>0 && effective('text/markdown')>=effective('text/html');
}

export function discoveryTarget(url: URL, accept=''): {redirect?: string; asset?: string; noindex?: boolean; contentType?: string; language?:string; page?:boolean} {
  if (url.pathname === '/data' || (url.pathname.endsWith('/') && url.pathname !== '/' && routes[url.pathname.slice(0, -1)])) {
    const path = url.pathname === '/data' ? '/coverage' : url.pathname.slice(0, -1);
    return {redirect: path + url.search};
  }
  if (agentFiles[url.pathname]) return {...agentFiles[url.pathname], noindex:true};
  if (discoveryFiles.includes(url.pathname)) return {asset: url.pathname};
  const alias=url.pathname.endsWith('.md');
  const path=alias ? url.pathname==='/index.md' ? '/' : url.pathname.slice(0,-3) : url.pathname;
  const page = routes[path];
  if (!page) return {};
  const lang = /^(zh|zh-hant|zh-hk)$/i.test(url.searchParams.get('lang') || '') ? 'zh-Hant' : 'en';
  if (alias && !page[lang+'-markdown']) return {};
  const markdown=Boolean(page[lang+'-markdown']) && (alias || prefersMarkdown(accept));
  const filtered = ['/playground','/','/coverage','/companies','/hkex','/sfc'].includes(path) && [...url.searchParams.keys()].some(key => key !== 'lang' && !key.startsWith('utm_'));
  return {asset: page[lang + (filtered ? '-filtered' : '') + (markdown ? '-markdown' : '')], noindex: alias || filtered || ['/terms', '/privacy'].includes(path), contentType:markdown ? 'text/markdown' : 'text/html',language:lang,page:true};
}
