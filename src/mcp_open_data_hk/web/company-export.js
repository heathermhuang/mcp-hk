/* Bounded, lossless JSON + spreadsheet-safe CSV. Hash the bytes actually packaged. */
const utf8=new TextEncoder();
export async function sha256(bytes){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');}
export function csvCell(value){
  let text=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);
  if(typeof value==='string'&&(/^[\s\u0000-\u001f\u007f-\u009f\u200b-\u200f]*[=+\-@]/.test(text)||/^0\d+$/.test(text)))text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
}
function crc32(bytes){let crc=0xffffffff;for(const b of bytes){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;}
function header(size){const bytes=new Uint8Array(size),view=new DataView(bytes.buffer);return {bytes,u16:(at,n)=>view.setUint16(at,n,true),u32:(at,n)=>view.setUint32(at,n,true)};}
export function zipStore(files){
  const local=[],central=[];let offset=0,total=0;
  for(const [name,bytes] of files){
    if(!/^[A-Za-z0-9._-]+$/.test(name))throw Error('INVALID_FILENAME');
    total+=bytes.length;if(total>16*1024*1024)throw Error('PAGE_EXPORT_TOO_LARGE');
    const filename=utf8.encode(name),crc=crc32(bytes),h=header(30),c=header(46);
    h.u32(0,0x04034b50);h.u16(4,20);h.u16(6,0x800);h.u16(12,33);h.u32(14,crc);h.u32(18,bytes.length);h.u32(22,bytes.length);h.u16(26,filename.length);
    c.u32(0,0x02014b50);c.u16(4,20);c.u16(6,20);c.u16(8,0x800);c.u16(14,33);c.u32(16,crc);c.u32(20,bytes.length);c.u32(24,bytes.length);c.u16(28,filename.length);c.u32(42,offset);
    local.push(h.bytes,filename,bytes);central.push(c.bytes,filename);offset+=30+filename.length+bytes.length;
  }
  const length=central.reduce((n,b)=>n+b.length,0),end=header(22);end.u32(0,0x06054b50);end.u16(8,files.length);end.u16(10,files.length);end.u32(12,length);end.u32(16,offset);
  return new Blob([...local,...central,end.bytes],{type:'application/zip'});
}
export async function pagePackage(envelope,context,notice){
  const rows=envelope?.data?.items,version=envelope?.meta?.version;
  if(!Array.isArray(rows)||rows.length>100||!rows.length||typeof version!=='string'||!/^[A-Za-z0-9._-]{1,100}$/.test(version)||typeof notice!=='string'||!((envelope.meta.view||'archive')==='latest_observed'?notice.includes('Companies Registry'):(envelope.meta.view||'archive')==='hkex_daily_summary'?notice.startsWith('Source: Hong Kong Exchanges and Clearing Limited (HKEX).'):['archive','webb_sdi_archive'].includes(envelope.meta.view||'archive')&&notice.includes('Webb')))throw Error('INVALID_PAGE_EXPORT');
  const columns=[...new Set(rows.flatMap(Object.keys))];
  const json=value=>utf8.encode(JSON.stringify(value,null,2)+'\n');
  const csv='\ufeff'+[columns.map(csvCell).join(','),...rows.map(row=>columns.map(k=>csvCell(row[k])).join(','))].join('\r\n')+'\r\n';
  const types=v=>v===null?'null':Array.isArray(v)?'array':typeof v==='number'&&Number.isInteger(v)?'integer':typeof v;
  const schema={columns:columns.map(name=>({name,jsonTypes:[...new Set(rows.map(r=>types(r[name]??null)))].sort()})),csv:{encoding:'UTF-8 with BOM',null:'empty cell',nestedValues:'JSON text',spreadsheetTextEscape:'Apostrophe prefix for formula-like strings and leading-zero digit strings. Use records.json for lossless source values.'}};
  const files=[['records.json',json(rows)],['records.csv',utf8.encode(csv)],['schema.json',json(schema)],['provenance.json',json({meta:envelope.meta,provenance:envelope.provenance,warnings:envelope.warnings})],['NOTICE.txt',utf8.encode(notice)]];
  const manifest={formatVersion:1,scope:'this_page',version,view:envelope.meta.view||'archive',currentVerification:false,rowCount:rows.length,selection:context,files:[]};
  for(const [name,bytes] of files)manifest.files.push({file:name,bytes:bytes.length,sha256:await sha256(bytes)});
  files.push(['manifest.json',json(manifest)]);
  const blob=zipStore(files);return {blob,manifest,sha256:await sha256(await blob.arrayBuffer()),filename:`companies-${version}-${context.family||'search'}-page.zip`};
}
