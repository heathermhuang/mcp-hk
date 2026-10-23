/** Optional backend wiring. No database or owner credential enters the gateway. */
export function curatedContainerEnv(env: object, origin: string): Record<string,string> {
  const token: unknown = Reflect.get(env,'CURATED_BACKEND_TOKEN');
  const disabled = {MCP_HK_CURATED_ORIGIN:'',MCP_HK_CURATED_TOKEN:''};
  if(typeof token !== 'string' || token.length < 32 || !origin) return disabled;
  try {
    const url = new URL(origin);
    if(url.protocol !== 'https:' || url.username || url.password || url.port || url.pathname !== '/' || url.search || url.hash) return disabled;
    return {MCP_HK_CURATED_ORIGIN:url.origin,MCP_HK_CURATED_TOKEN:token};
  } catch {return disabled;}
}
