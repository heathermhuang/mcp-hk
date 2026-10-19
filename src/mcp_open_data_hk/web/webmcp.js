/* Read-only, first-party tools. This does not add authentication or write access. */
(() => {
  const context = document.modelContext || navigator.modelContext;
  if (!context?.registerTool) return;
  const lifecycle = new AbortController();
  window.addEventListener('pagehide', event => { if (!event.persisted) lifecycle.abort(); }, {once:true});
  const validObject = value => value && typeof value === 'object' && !Array.isArray(value);
  async function read(path) {
    const response = await fetch(path, {headers:{Accept:'application/json'},signal:AbortSignal.timeout(90000),credentials:'omit',redirect:'error'});
    if (!response.ok) throw new Error('mcp.hk public read failed (HTTP '+response.status+'). Respect Retry-After; a source failure is not an empty dataset.');
    const reader=response.body.getReader(), chunks=[];let length=0;
    for (;;) {
      const {done,value}=await reader.read();if(done)break;
      length+=value.byteLength;
      if(length>2*1024*1024){await reader.cancel();throw new Error('mcp.hk response exceeded the public tool limit.');}
      chunks.push(value);
    }
    const bytes=new Uint8Array(length);let offset=0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
    const payload=JSON.parse(new TextDecoder().decode(bytes));
    return {content:[{type:'text',text:JSON.stringify(payload)}]};
  }
  const tools = [{
    name:'search_hong_kong_datasets',
    description:'Search Hong Kong government and independent data catalogues. A catalogue entry does not guarantee readable or semantically verified records. Inspect source access, provenance and freshness before use.',
    inputSchema:{type:'object',properties:{q:{type:'string',minLength:1,maxLength:200,description:'Dataset, provider or topic to search'},access:{type:'string',enum:['all','connected','sources'],default:'all'},limit:{type:'integer',minimum:1,maximum:10,default:5}},required:['q'],additionalProperties:false},
    annotations:{readOnlyHint:true,destructiveHint:false},
    execute:async input=>{
      if(!validObject(input) || Object.keys(input).some(key=>!['q','access','limit'].includes(key)) || typeof input.q!=='string' || !input.q.trim() || input.q.length>200) throw new TypeError('Supply a query of 1–200 characters and only the documented fields.');
      const access=input.access ?? 'all',limit=input.limit ?? 5;
      if(!['all','connected','sources'].includes(access) || !Number.isInteger(limit) || limit<1 || limit>10) throw new TypeError('Invalid access mode or result limit.');
      return read('/api/v1/catalogue/datasets?'+new URLSearchParams({q:input.q.trim(),access,limit:String(limit)}));
    }
  },{
    name:'get_hong_kong_data_packs',
    description:'List mcp.hk data packs, providers and documented read capabilities. Public read-only access requires no API key; original provider terms and request limits apply.',
    inputSchema:{type:'object',properties:{},additionalProperties:false},
    annotations:{readOnlyHint:true,destructiveHint:false},
    execute:async(input={})=>{
      if(!validObject(input) || Object.keys(input).length)throw new TypeError('This tool accepts no arguments.');
      return read('/api/v1/packs');
    }
  }];
  for(const tool of tools) {
    try { Promise.resolve(context.registerTool(tool,{signal:lifecycle.signal})).catch(()=>console.warn('mcp.hk WebMCP registration unavailable.')); }
    catch { console.warn('mcp.hk WebMCP registration unavailable.'); }
  }
})();
