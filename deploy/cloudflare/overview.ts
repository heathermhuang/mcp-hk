/** Dated public counts, served without waking the query container. */
export const OVERVIEW_KEY = 'public/overview.json';
type OverviewEnv = Pick<Env, 'BACKUPS' | 'ASSETS' | 'RELEASE_COMMIT'>;
function count(value: unknown): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) throw new Error('Invalid overview count');
  return value;
}
export function compactOverview(value: unknown, asOf = new Date().toISOString()) {
  if (!value || typeof value !== 'object') throw new Error('Invalid coverage response');
  const c = value as {generation?: unknown; datasets?: {discovered?: unknown}; resources?: {discovered?: unknown; byStatus?: {queryable?: unknown}}};
  if (typeof c.generation !== 'string' || !c.generation || c.generation.length > 200) throw new Error('Invalid inventory generation');
  const datasets = count(c.datasets?.discovered), resources = count(c.resources?.discovered), queryable = count(c.resources?.byStatus?.queryable ?? 0);
  if (queryable > resources) throw new Error('Inconsistent overview counts');
  return {generation: c.generation, asOf, datasets: {discovered: datasets}, resources: {discovered: resources, byStatus: {queryable}}, allGovernmentDataConnected: false};
}
export async function saveOverview(env: Pick<Env, 'BACKUPS'>, value: unknown) {
  const overview = compactOverview(value);
  await env.BACKUPS.put(OVERVIEW_KEY, JSON.stringify(overview), {httpMetadata: {contentType: 'application/json'}});
  return {status: 'published', asOf: overview.asOf, generation: overview.generation};
}
export async function serveOverview(env: OverviewEnv, request: Request) {
  if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405, headers: {Allow: 'GET, HEAD'}});
  let response: Response, source = 'published';
  try {
    const object = await env.BACKUPS.get(OVERVIEW_KEY);
    if (!object) throw new Error('No published overview');
    response = new Response(object.body);
  } catch {
    const url = new URL('/overview.json', request.url);
    response = await env.ASSETS.fetch(new Request(url)); source = 'release-snapshot';
  }
  const headers = new Headers(response.headers);
  headers.set('Content-Type', 'application/json'); headers.set('Cache-Control', 'public, max-age=60');
  headers.set('X-Mcp-Overview', source); headers.set('X-Mcp-Release', env.RELEASE_COMMIT);
  headers.set('X-Content-Type-Options', 'nosniff'); headers.set('Strict-Transport-Security', 'max-age=31536000');
  if (request.method === 'HEAD') { await response.body?.cancel(); return new Response(null, {status: response.status, headers}); }
  return new Response(response.body, {status: response.status, headers});
}
