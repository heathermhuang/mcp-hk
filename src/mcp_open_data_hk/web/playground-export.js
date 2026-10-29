import {csvCell,sha256,zipStore} from './export-bytes.js';
import {pagePackage} from './company-export.js';
const utf8=new TextEncoder();
function csvScalar(cell){
  if(['integer','float'].includes(cell.kind)){
    const raw=cell.text,value=Number(raw),digits=raw.split(/[eE]/)[0].replace(/[.\-]/g,'').replace(/^0+/,'').length;
    // Valid numeric literals cannot execute a formula. Force text when common
    // spreadsheets would round the source value, or erase negative zero.
    if(!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(raw))throw Error('INVALID_SCALAR');
    return !Number.isFinite(value)||Math.abs(value)>Number.MAX_SAFE_INTEGER||digits>15||Object.is(value,-0)?csvCell("'"+raw):'"'+raw+'"';
  }
  return csvCell(cell.kind==='missing'||cell.kind==='null'?null:cell.text);
}
export function exportPolicy(result,recipe){
  if(!result?.rows?.length||!result.presentation||result.expired)return false;
  if(recipe.resource){
    return result.envelopes.every(p=>p.dataset?.providerType==='government'&&p.resource?.catalogue==='DATA.GOV.HK'&&p.provenance?.length&&p.provenance.every(s=>s.termsUrl==='https://data.gov.hk/en/terms-and-conditions')&&!['restricted','unsupported'].includes(p.resource.validation?.status));
  }
  return ['company_registry','enigma','hkex_daily','webb_sdi'].includes(recipe.family)&&result.envelopes.every(p=>p.meta?.version&&p.data?.items?.length);
}
export async function evidencePackage(result,recipe,signal){
  if(!exportPolicy(result,recipe))throw Error('EXPORT_NOT_AUTHORIZED');
  const p=result.presentation,notices=[];
  for(const envelope of result.envelopes){
    if(recipe.resource){notices.push(envelope.provenance.map(s=>[s.attribution,s.termsUrl,s.originalResourceUrl].join('\n')).join('\n\n'));continue;}
    const view=envelope.meta.view||'archive',endpoint=view==='latest_observed'?null:view==='hkex_daily_summary'?'/api/v1/hkex/latest/notice':view==='webb_sdi_archive'?'/api/v1/hkex/archive/notice':'/api/v1/companies/notice';
    let notice='Government of the HKSAR / Companies Registry / DATA.GOV.HK.\nhttps://data.gov.hk/en/terms-and-conditions';
    if(endpoint){const response=await fetch(endpoint,{signal});if(!response.ok)throw Error('NOTICE_UNAVAILABLE');notice=await response.text();}
    // Preserve the established source-specific notice and view policy checks.
    await pagePackage(envelope,{family:'playground-page'},notice);
    notices.push(notice);
  }
  if(signal.aborted)throw new DOMException('Aborted','AbortError');
  const csv='\ufeff'+[p.columns.map(csvCell).join(','),...p.rows.map(row=>row.map(csvScalar).join(','))].join('\r\n')+'\r\n';
  const json=value=>utf8.encode(JSON.stringify(value,null,2)+'\n');
  const files=[['records.json',utf8.encode(p.recordsJson+'\n')],['records.csv',utf8.encode(csv)],['schema.json',json({codec:1,columns:p.columns,scalarCells:p.rows,sourceSchemas:result.envelopes.map(e=>e.schema||null),precision:'Exact server-parsed JSON; reader precision limits still apply.',csv:{nullAndMissing:'empty cell; consult JSON and scalarCells',textEscape:'Apostrophe prefix for formula-like text, leading-zero strings, unsafe/precise numbers and negative zero; JSON is authoritative.'}})],['query.json',json(recipe)],['provenance.json',json({sources:result.envelopes.map(({meta,provenance,warnings,coverage,quality,validationFreshness})=>({meta,provenance,warnings,coverage,quality,validationFreshness})),unavailableSources:result.errors||[]})],['NOTICE.txt',utf8.encode(notices.join('\n\n---\n\n'))]];
  const manifest={formatVersion:1,scope:'displayed_page',rowCount:result.rows.length,unavailableSources:result.errors||[],versions:result.envelopes.map(e=>e.meta?.version||null),chart:recipe.view?.type==='chart'?{...recipe.view,scope:'loaded_page'}:null,files:[]};
  for(const [file,bytes] of files)manifest.files.push({file,bytes:bytes.length,sha256:await sha256(bytes)});
  files.push(['manifest.json',json(manifest)]);
  const blob=zipStore(files);return {blob,manifest,sha256:await sha256(await blob.arrayBuffer()),filename:'mcp-hk-'+recipe.family+'-page.zip'};
}
