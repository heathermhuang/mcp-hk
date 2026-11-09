import registry from '../../src/mcp_open_data_hk/source-relay-targets.json' with {type:'json'};

const targets: Readonly<Record<string,string>>=Object.freeze(registry.targets);
type TransportContract={template:string;parameters:Record<string,string>;arrivals:boolean};
const transport: Readonly<Record<string,TransportContract>>=Object.freeze(registry.transport);
const hosts=new Set(['xpms.hyd.gov.hk','webcat.hkpl.gov.hk','data.cr.gov.hk','data.smartplay.lcsd.gov.hk','rt.data.gov.hk']);
export function approvedSource(resourceId: string,selection?:URLSearchParams): string | undefined {
  if(!/^[a-f0-9]{32}$/.test(resourceId))return;
  const contract=Object.hasOwn(transport,resourceId)?transport[resourceId]:undefined;
  let target=Object.hasOwn(targets,resourceId)?targets[resourceId]:undefined;
  if(contract){
    if(!selection||selection.get('resourceId')!==resourceId)return;
    const names=['resourceId',...Object.keys(contract.parameters)];
    if([...selection.keys()].some(k=>!names.includes(k))||names.some(k=>selection.getAll(k).length!==1))return;
    target=contract.template;
    for(const [name,rule]of Object.entries(contract.parameters)){
      const value=selection.get(name)!;const matched=new RegExp('^(?:'+rule+')$','u').exec(value);
      if(!matched||matched[0].length!==value.length)return;
      target=target.replace('{'+name+'}',encodeURIComponent(value));
    }
  }else if(selection&&([...selection.keys()].some(k=>k!=='resourceId')||selection.getAll('resourceId').length!==1))return;
  if(!target)return;
  const url=new URL(target);
  if(url.protocol!=='https:'||!hosts.has(url.hostname)||url.username||url.password||(url.port&&url.port!=='443'))return;
  return target;
}

/** Operator-authenticated caller only. No arbitrary URL, credential or body forwarding. */
export async function relayApprovedSource(request: Request, fetcher: typeof fetch=fetch){
  if(request.method!=='GET')return new Response('Method not allowed',{status:405});
  const selection=new URL(request.url).searchParams,resourceId=selection.get('resourceId')||'';
  const target=approvedSource(resourceId,selection),contract=Object.hasOwn(transport,resourceId)?transport[resourceId]:undefined;
  if(!target)return new Response('Unknown approved source',{status:404});
  const headers=new Headers({Accept:'application/json,application/rss+xml,application/xml;q=0.9,*/*;q=0.8','Accept-Encoding':'identity','User-Agent':'mcp.hk-resources/0.4 (+https://mcp.hk)'});
  for(const key of ['If-None-Match','If-Modified-Since']){const value=request.headers.get(key);if(value)headers.set(key,value);}
  if(contract?.arrivals){headers.delete('If-None-Match');headers.delete('If-Modified-Since');headers.set('Cache-Control','no-cache');}
  let current=target;
  const signal=AbortSignal.timeout(25000);
  try{
    for(let hop=0;hop<4;hop++){
      const upstream=await fetcher(current,{method:'GET',redirect:'manual',headers,signal});
      if([301,302,303,307,308].includes(upstream.status)){
        if(contract){await upstream.body?.cancel();return Response.json({error:{code:'SOURCE_REDIRECT_REJECTED'}},{status:502});}
        const location=upstream.headers.get('Location');await upstream.body?.cancel();
        if(!location)break;const next=new URL(location,current),original=new URL(target);
        if(next.protocol!=='https:'||next.hostname!==original.hostname||next.username||next.password||(next.port&&next.port!=='443'))break;
        current=next.href;continue;
      }
      const resultHeaders=new Headers({'Cache-Control':'no-store','X-Mcp-Source-Transport':'approved-worker-relay'});
      for(const name of ['Content-Type','Content-Encoding','ETag','Last-Modified']){const value=upstream.headers.get(name);if(value)resultHeaders.set(name,value);}
      // Stream unchanged. The authenticated reader enforces decoded 8/128 MB
      // limits and cancellation; no unbounded body is buffered in the Worker.
      return new Response(upstream.body,{status:upstream.status,headers:resultHeaders});
    }
    return Response.json({error:{code:'SOURCE_REDIRECT_REJECTED'}},{status:502});
  }catch{return Response.json({error:{code:'SOURCE_RELAY_UNAVAILABLE'}},{status:502});}
}
