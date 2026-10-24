
const ROOT='exports/companies', VERSION=/^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/, SHA=/^[a-f0-9]{64}$/;
const TABLES=['entities','entity_identifiers','entity_names','officer_appointments','licences','licence_relationships','source_references'];
type Part={file:string;bytes:number;sha256:string};
type Manifest={version:string;archive:{file:string;bytes:number;sha256:string;parts:Part[]};[key:string]:unknown};
const hex=(bytes:ArrayBuffer)=>Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
function digester(){const stream=new crypto.DigestStream('SHA-256'),writer=stream.getWriter(),value=stream.digest.then(hex);value.catch(()=>{});return {write:(v:Uint8Array)=>writer.write(v),finish:async()=>{await writer.close();return value;},abort:async()=>{await writer.abort().catch(()=>{});}};}
const record=(x:unknown):x is Record<string,unknown>=>Boolean(x)&&typeof x==='object'&&!Array.isArray(x);
const error=(code:string,status=503)=>Response.json({error:{code,message:'The verified archive is unavailable. Search results remain available.'}},{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});

async function json(bucket:R2Bucket,key:string):Promise<unknown> {
  const object=await bucket.get(key);
  if(!object)throw new Error('not_found');
  if(object.size>1024*1024){await object.body.cancel();throw new Error('manifest_size');}
  const reader=object.body.getReader();let size=0;const parts:Uint8Array[]=[];
  try {while(true){const r=await reader.read();if(r.done)break;size+=r.value.length;if(size>1024*1024)throw new Error('manifest_size');parts.push(r.value);}}
  catch(e){await reader.cancel().catch(()=>{});throw e;}
  const bytes=new Uint8Array(size);let at=0;for(const part of parts){bytes.set(part,at);at+=part.length;}
  return JSON.parse(new TextDecoder('utf-8',{fatal:true,ignoreBOM:false}).decode(bytes));
}
function manifest(value:unknown,version:string,sha:string):Manifest {
  if(!record(value)||value.formatVersion!==1||value.version!==version||value.view!=='archive'||value.scope!=='complete_approved_subset'||value.currentVerification!==false||!record(value.source)||!record(value.source.counts)||typeof value.noticeSha256!=='string'||!SHA.test(value.noticeSha256)||!record(value.schema)||!Array.isArray(value.tables)||value.tables.length!==TABLES.length||!record(value.archive))throw new Error('manifest_contract');
  const a=value.archive;
  if(a.file!=='companies.tar.gz'||a.sha256!==sha||typeof a.bytes!=='number'||!Number.isSafeInteger(a.bytes)||a.bytes<1||a.bytes>2*1024**3||!Array.isArray(a.parts)||!a.parts.length||a.parts.length>128)throw new Error('archive_contract');
  const parts:Part[]=a.parts.map((p:unknown,i:number)=>{
    if(!record(p)||p.file!==`part-${String(i).padStart(3,'0')}`||typeof p.bytes!=='number'||!Number.isSafeInteger(p.bytes)||p.bytes<1||p.bytes>16*1024*1024||typeof p.sha256!=='string'||!SHA.test(p.sha256))throw new Error('part_contract');
    return {file:p.file,bytes:p.bytes,sha256:p.sha256};
  });
  if(parts.reduce((n,p)=>n+p.bytes,0)!==a.bytes)throw new Error('archive_size');
  for(const [i,t] of value.tables.entries())if(!record(t)||t.name!==TABLES[i]||t.file!==TABLES[i]+'.ndjson'||typeof t.rows!=='number'||!Number.isSafeInteger(t.rows)||t.rows<0||!record(value.source)||!record(value.source.counts)||t.rows!==value.source.counts[TABLES[i]]||typeof t.sha256!=='string'||!SHA.test(t.sha256))throw new Error('table_contract');
  return {...value,version,archive:{file:'companies.tar.gz',bytes:a.bytes,sha256:sha,parts}};
}

/** One isolated semaphore per named controller. Never buffer the archive or query PG. */
export function companyDownloads(bucket:R2Bucket) {
  let active=0;
  return async(request:Request):Promise<Response|null>=>{
    const url=new URL(request.url);
    if(!url.pathname.startsWith('/downloads/companies/'))return null;
    if(!['GET','HEAD'].includes(request.method))return new Response(null,{status:405,headers:{Allow:'GET, HEAD'}});
    let version:string,sha:string,file:string;
    try {
      if(url.pathname==='/downloads/companies/manifest.json'){
        const chosen=url.searchParams.get('version');if(chosen&&!VERSION.test(chosen))return error('INVALID_VERSION',400);
        const pointer=await json(bucket,chosen?`${ROOT}/${chosen}/current.json`:`${ROOT}/latest.json`);
        if(!record(pointer)||typeof pointer.version!=='string'||!VERSION.test(pointer.version)||typeof pointer.sha256!=='string'||!SHA.test(pointer.sha256)||(chosen&&pointer.version!==chosen))throw new Error('pointer_contract');
        version=pointer.version;sha=pointer.sha256;file='manifest.json';
      }else{
        const match=url.pathname.match(/^\/downloads\/companies\/([A-Za-z0-9][A-Za-z0-9._-]{0,99})\/([a-f0-9]{64})\/(manifest\.json|schema\.json|NOTICE\.txt|companies\.tar\.gz)$/);
        if(!match)return error('DOWNLOAD_NOT_FOUND',404);
        [,version,sha,file]=match;
      }
      const prefix=`${ROOT}/${version}/${sha}`;
      const data=manifest(await json(bucket,`${prefix}/manifest.json`),version,sha);
      const base=`/downloads/companies/${version}/${sha}`;
      const publicData={...data,downloadUrl:base+'/companies.tar.gz',manifestUrl:base+'/manifest.json',schemaUrl:base+'/schema.json',noticeUrl:base+'/NOTICE.txt'};
      if(file==='manifest.json'||file==='schema.json'){
        const body=JSON.stringify(file==='manifest.json'?publicData:data.schema);
        return new Response(request.method==='HEAD'?null:body,{headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
      }
      if(file==='NOTICE.txt'){
        const object=await bucket.get(`${prefix}/NOTICE.txt`);if(!object||object.size>100000){await object?.body.cancel();throw new Error('notice_missing');}
        const bytes=await object.arrayBuffer();if(hex(await crypto.subtle.digest('SHA-256',bytes))!==data.noticeSha256)throw new Error('notice_checksum');
        return new Response(request.method==='HEAD'?null:bytes,{headers:{'Content-Type':'text/plain; charset=utf-8','X-Content-Type-Options':'nosniff'}});
      }
      if(request.headers.has('range'))return new Response(null,{status:416,headers:{'Content-Range':`bytes */${data.archive.bytes}`,'Accept-Ranges':'none'}});
      if(active>=2)return Response.json({error:{code:'DOWNLOAD_BUSY',message:'Two archive downloads are active. Try again shortly.'}},{status:429,headers:{'Retry-After':'30','Cache-Control':'no-store'}});
      // Missing/truncated parts fail before a successful response. Body reads also hash
      // each part and the complete archive; corruption aborts the stream, never closes it.
      for(let i=0;i<data.archive.parts.length;i+=4){await Promise.all(data.archive.parts.slice(i,i+4).map(async p=>{const head=await bucket.head(`${prefix}/${p.file}`);if(!head||head.size!==p.bytes)throw new Error('part_missing');}));}
      const headers={'Content-Type':'application/gzip','Content-Disposition':`attachment; filename="companies-${version}.tar.gz"`,'X-Content-SHA256':sha,'X-Expected-Bytes':String(data.archive.bytes),'X-Content-Type-Options':'nosniff','Accept-Ranges':'none','Cache-Control':'no-store'};
      if(request.method==='HEAD')return new Response(null,{headers});
      if(active>=2)return error('DOWNLOAD_BUSY',429);
      active++;let released=false;const release=()=>{if(!released){released=true;active--;}};
      async function* bytes(){
        const whole=digester();let total=0;
        try{
          for(let index=0;index<data.archive.parts.length;index++){
            const part=data.archive.parts[index], object=await bucket.get(`${prefix}/${part.file}`);if(!object||object.size!==part.bytes)throw new Error('part_changed');
            const reader=object.body.getReader(), hash=digester();let pending:Uint8Array|undefined,size=0,ended=false;
            try {
              while(true){const next=await reader.read();if(next.done){ended=true;break;}size+=next.value.length;total+=next.value.length;if(size>part.bytes||total>data.archive.bytes)throw new Error('overflow');await hash.write(next.value);await whole.write(next.value);if(pending)yield pending;pending=next.value;}
              if(size!==part.bytes||await hash.finish()!==part.sha256)throw new Error('part_checksum');
              if(index===data.archive.parts.length-1&&(total!==data.archive.bytes||await whole.finish()!==sha))throw new Error('archive_checksum');
              if(pending)yield pending;
            }finally{if(!ended)await reader.cancel().catch(()=>{});await hash.abort();reader.releaseLock();}
          }
        }finally{await whole.abort();release();}
      }
      const iterator=bytes();
      const body=new ReadableStream<Uint8Array>({async pull(controller){try{const next=await iterator.next();if(next.done){release();controller.close();}else controller.enqueue(next.value);}catch(e){release();controller.error(e);}},async cancel(){release();await iterator.return(undefined);}});
      return new Response(body,{headers});
    }catch(e){return error(e instanceof Error&&e.message==='not_found'?'DOWNLOAD_VERSION_NOT_FOUND':'DOWNLOAD_UNAVAILABLE',e instanceof Error&&e.message==='not_found'?404:503);}
  };
}

/** Called only under the authenticated controller's maintenance lease. No public key input. */
export async function publishCompanyDownload(bucket:R2Bucket, input:unknown){
  if(!record(input)||typeof input.version!=='string'||!VERSION.test(input.version)||typeof input.sha256!=='string'||!SHA.test(input.sha256)||![null,'string'].includes(input.expectedVersionHash===null?null:typeof input.expectedVersionHash)||![null,'string'].includes(input.expectedLatestHash===null?null:typeof input.expectedLatestHash))throw new Error('INVALID_PUBLICATION');
  const version=input.version,sha=input.sha256,prefix=`${ROOT}/${version}/${sha}`;
  const data=manifest(await json(bucket,`${prefix}/manifest.json`),version,sha);
  const previous=async(key:string)=>{try{const value=await json(bucket,key);if(!record(value)||typeof value.sha256!=='string'||!SHA.test(value.sha256))throw new Error('INVALID_POINTER');return value.sha256;}catch(e){if(e instanceof Error&&e.message==='not_found')return null;throw e;}};
  const versionKey=`${ROOT}/${version}/current.json`,latestKey=`${ROOT}/latest.json`;
  if(await previous(versionKey)!==input.expectedVersionHash||await previous(latestKey)!==input.expectedLatestHash)throw new Error('PUBLICATION_CONFLICT');
  for(let i=0;i<data.archive.parts.length;i+=4)await Promise.all(data.archive.parts.slice(i,i+4).map(async p=>{const object=await bucket.head(`${prefix}/${p.file}`);if(!object||object.size!==p.bytes)throw new Error('INCOMPLETE_EXPORT');}));
  const notice=await bucket.get(`${prefix}/NOTICE.txt`);if(!notice||notice.size>100000){await notice?.body.cancel();throw new Error('INCOMPLETE_NOTICE');}if(hex(await crypto.subtle.digest('SHA-256',await notice.arrayBuffer()))!==data.noticeSha256)throw new Error('NOTICE_CHECKSUM');
  const value=JSON.stringify({version,sha256:sha});
  await bucket.put(versionKey,value,{httpMetadata:{contentType:'application/json'}});
  await bucket.put(latestKey,value,{httpMetadata:{contentType:'application/json'}});
  return {published:true,version,sha256:sha,manifestUrl:`/downloads/companies/${version}/${sha}/manifest.json`};
}
