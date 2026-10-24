import {boundedResponse} from './response-policy.ts';
import registry from '../../src/mcp_open_data_hk/source-relay-targets.json' with {type:'json'};

const targets: Readonly<Record<string,string>>=Object.freeze(registry.targets);
const hosts=new Set(['xpms.hyd.gov.hk','webcat.hkpl.gov.hk','data.cr.gov.hk','data.smartplay.lcsd.gov.hk','rt.data.gov.hk']);
export function approvedSource(resourceId: string): string | undefined {
  if(!/^[a-f0-9]{32}$/.test(resourceId)||!Object.hasOwn(targets,resourceId))return;
  const target=targets[resourceId],url=new URL(target);
  if(url.protocol!=='https:'||!hosts.has(url.hostname)||url.username||url.password||(url.port&&url.port!=='443'))return;
  return target;
}

/** Operator-authenticated caller only. No arbitrary URL, credential or body forwarding. */
export async function relayApprovedSource(request: Request, fetcher: typeof fetch=fetch){
  if(request.method!=='GET')return new Response('Method not allowed',{status:405});
  const target=approvedSource(new URL(request.url).searchParams.get('resourceId')||'');
  if(!target)return new Response('Unknown approved source',{status:404});
  const headers=new Headers({Accept:'application/json,application/rss+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Encoding':'identity','User-Agent':'mcp.hk-resources/0.4 (+https://mcp.hk)'});
  for(const key of ['If-None-Match','If-Modified-Since']){const value=request.headers.get(key);if(value)headers.set(key,value);}
  let current=target;
  const signal=AbortSignal.timeout(25000);
  try{
    for(let hop=0;hop<4;hop++){
      const upstream=await fetcher(current,{method:'GET',redirect:'manual',headers,signal});
      if([301,302,303,307,308].includes(upstream.status)){
        const location=upstream.headers.get('Location');await upstream.body?.cancel();
        if(!location)break;const next=new URL(location,current),original=new URL(target);
        if(next.protocol!=='https:'||next.hostname!==original.hostname||next.username||next.password||(next.port&&next.port!=='443'))break;
        current=next.href;continue;
      }
      const resultHeaders=new Headers({'Cache-Control':'no-store','X-Mcp-Source-Transport':'approved-worker-relay'});
      for(const name of ['Content-Type','Content-Encoding','ETag','Last-Modified']){const value=upstream.headers.get(name);if(value)resultHeaders.set(name,value);}
      // Operator-only diagnostic relay: edge caps transport bytes and deadline.
      // The reader independently caps decoded bytes; public reads use grants.
      return boundedResponse(new Response(upstream.body,{status:upstream.status,headers:resultHeaders}),128_000_000);
    }
    return Response.json({error:{code:'SOURCE_REDIRECT_REJECTED'}},{status:502});
  }catch{return Response.json({error:{code:'SOURCE_RELAY_UNAVAILABLE'}},{status:502});}
}
