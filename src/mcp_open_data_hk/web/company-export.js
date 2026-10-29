import {csvCell,sha256,zipStore} from './export-bytes.js';
export {csvCell,sha256,zipStore} from './export-bytes.js';
const utf8=new TextEncoder();
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
