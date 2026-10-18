/** Authenticated diagnostics only: two immutable public HTTPS targets, no URL input. */
const targets = {
  xpms: 'https://xpms.hyd.gov.hk/psi/datasets/XP_DATA.json',
  hko: 'https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en',
};

export async function probePublicSource(source: string, fetcher: typeof fetch = fetch) {
  if (!Object.hasOwn(targets,source)) return Response.json({error:{code:'UNKNOWN_SOURCE_PROBE'}},{status:404});
  const url=targets[source as keyof typeof targets], started=Date.now();
  try {
    const response=await fetcher(url,{method:'GET',redirect:'manual',headers:{Accept:'application/json','Accept-Encoding':'identity','User-Agent':'mcp.hk-source-diagnostics/1'},signal:AbortSignal.timeout(15000)});
    const reader=response.body?.getReader();let length=0;const chunks: Uint8Array[]=[];
    if(reader)try{
      for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>8000000)throw Error('SOURCE_TOO_LARGE');chunks.push(value);}
    }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
    const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
    let jsonKind='not_json',records: number | null=null;
    try{const value=JSON.parse(new TextDecoder().decode(bytes));jsonKind=Array.isArray(value)?'array':typeof value;records=Array.isArray(value)?value.length:1;}catch{/* A non-JSON response is diagnostic evidence, never successful source records. */}
    return Response.json({source,url,sourceStatus:response.status,bytes:length,jsonKind,records,elapsedSeconds:(Date.now()-started)/1000},{headers:{'Cache-Control':'no-store'}});
  }catch(error){return Response.json({source,sourceStatus:null,errorType:error instanceof DOMException?error.name:'SOURCE_PROBE_FAILED',elapsedSeconds:(Date.now()-started)/1000},{headers:{'Cache-Control':'no-store'}});}
}
