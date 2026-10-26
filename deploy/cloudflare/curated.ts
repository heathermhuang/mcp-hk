/** Optional backend wiring. No database or owner credential enters the gateway. */
export function curatedContainerEnv(env: object, origin: string): Record<string,string> {
  const token: unknown = Reflect.get(env,'CURATED_BACKEND_TOKEN');
  const disabled = {MCP_HK_CURATED_ORIGIN:'',MCP_HK_CURATED_TOKEN:''};
  if(typeof token !== 'string' || token.length < 32 || !origin) return disabled;
  try {
    const url = new URL(origin);
    if(url.protocol !== 'https:' || url.username || url.password || url.port || url.pathname !== '/' || url.search || url.hash) return disabled;
    const policy=Reflect.get(env,'SFC_POLICY_JSON'),policySha=Reflect.get(env,'SFC_POLICY_SHA256');
    const sfc:Record<string,string>=typeof policy==='string'&&new TextEncoder().encode(policy).length<=32768&&typeof policySha==='string'&&/^[a-f0-9]{64}$/.test(policySha)?{MCP_HK_SFC_POLICY_JSON:policy,MCP_HK_SFC_POLICY_SHA256:policySha}:{};
    return {MCP_HK_CURATED_ORIGIN:url.origin,MCP_HK_CURATED_TOKEN:token,...(Reflect.get(env,'WEBB_SDI_ARCHIVE_ENABLED')==='true'?{MCP_HK_WEBB_SDI_ENABLED:'true'}:{}),...(Reflect.get(env,'HKEX_DAILY_ENABLED')==='true'?{MCP_HK_HKEX_DAILY_ENABLED:'true'}:{}),...sfc};
  } catch {return disabled;}
}
