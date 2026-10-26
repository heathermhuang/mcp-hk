const $ = id => document.getElementById(id);
const t = key => window.MhkI18n.t(key);
let status, version, selection, nextCursor, generation = 0;
const cache = new Map();
const states = {original:'hkexOriginal',amendment:'hkexAmendment',superseded:'hkexSuperseded',withdrawn:'hkexWithdrawnState'};
const terms = {long:'hkexLong',short:'hkexShort',lending_pool:'hkexLending',direct:'hkexDirect',deemed:'hkexDeemed',indirect:'hkexIndirect',unknown:'hkexUnknown',before:'hkexBefore',after:'hkexAfter',declared:'hkexDeclared',issuer_shares:'hkexIssuerShares',associated_shares:'hkexAssociatedShares',debenture:'hkexDebenture'};
const basis = value => t({event:"hkexEvent",filed:"hkexFiled",published:"hkexPublished"}[value]);
const label = value => terms[value] ? t(terms[value]) : value ?? t('hkexUnknown');
function text(tag, value) {const e = document.createElement(tag);e.textContent=value??t('hkexUnknown');return e;}
function factualTable(target, headers, rows, aria) {
  const wrap=text('div','');wrap.className='hkex-table';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',t(aria));
  const table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');
  for(const key of headers)tr.append(text('th',t(key)));head.append(tr);table.append(head);
  const body=document.createElement('tbody');for(const values of rows){const row=document.createElement('tr');for(const value of values){const cell=text('td',value);cell.style.whiteSpace='pre-line';row.append(cell);}body.append(row);}table.append(body);wrap.append(table);$(target).replaceChildren(wrap);
}
const subjectName = row => document.documentElement.lang.startsWith('zh')&&row.subject_name_zh_hant?row.subject_name_zh_hant:row.subject;
function button(value, fn) {const e=text('button',value);e.className='mhk-button mhk-secondary';e.type='button';e.addEventListener('click',fn);return e;}
async function fetchJSON(path, params={}) {
  const url = new URL('/api/v1/hkex/'+path,location.origin);
  for(const [key,value] of Object.entries(params)) if(value!=null)url.searchParams.set(key,value);
  const response=await fetch(url,{cache:'no-store'});if(!response.ok)throw new Error('unavailable');return response.json();
}
function clearData(){cache.clear();version=null;selection=null;nextCursor=null;$('hkex-workspace').hidden=true;$('hkex-issuers').replaceChildren();$('hkex-list').replaceChildren();$('hkex-detail').hidden=true;$('hkex-filings').hidden=true;for(const id of ['hkex-dates','hkex-interests','hkex-particulars-table','hkex-controls-table','hkex-revisions'])$(id).replaceChildren();$('hkex-particulars').hidden=true;$('hkex-controls').hidden=true;$('hkex-detail-heading').textContent=t('hkexDetail');}
async function check(){
  const turn=++generation;
  try {
    const result=await fetchJSON('browser/status');if(turn!==generation)return;
    status=result;
    const allowed=result.state==='accepted'&&result.acceptedVersion&&result.modes?.browser==='allowed';
    if(!allowed){clearData();$('hkex-status').textContent=t('hkexGated');$('hkex-coverage').textContent='';return;}
    if(version&&version!==result.acceptedVersion)clearData();
    $('hkex-status').textContent=t('hkexAccepted');$('hkex-workspace').hidden=false;
    const w=result.coverage?.window;
    $('hkex-coverage').textContent=w?`${w.issuer_id} · ${w.start} ≤ ${basis(w.basis)} < ${w.end} · ${t('hkexEndExclusive')} · ${result.acceptedVersion}`:'';
  }catch{if(turn===generation){clearData();$('hkex-status').textContent=t('hkexUnavailable');}}
}
async function search(event){
  event?.preventDefault();const turn=++generation;
  try{
    const result=await fetchJSON('browser/issuers',{stockCode:$('hkex-stock').value,version:status.acceptedVersion});if(turn!==generation)return;
    version=result.version;cache.clear();$('hkex-detail').hidden=true;$('hkex-filings').hidden=true;
    $('hkex-issuers').replaceChildren(...result.data.map(row=>button(`${row.name} · ${row.securities.map(x=>`${x.stock_code??t('hkexUnknown')} (${x.share_class??t('hkexUnknown')})`).join(', ')}`,()=>list(row.id))));
    $('hkex-message').textContent=result.data.length?'':t('hkexNoIssuer');
  }catch{if(turn===generation)$('hkex-message').textContent=t('hkexFailed');}
}
async function list(issuer, cursor=null){
  const turn=++generation,w=status.coverage.window;
  try{
    const result=await fetchJSON('browser/disclosures',{issuerId:issuer,start:w.start,end:w.end,basis:w.basis,channel:w.channel,version,cursor});if(turn!==generation)return;
    selection=issuer;nextCursor=result.nextCursor;
    $('hkex-filings').hidden=false;$('hkex-list').replaceChildren(...result.data.map(row=>{cache.set(row.serial,row);return button(`${row.serial} · ${subjectName(row)} · ${t(states[row.state])}`,()=>detail(row.serial));}));
    $('hkex-window').textContent=`${result.coverage.complete?t('hkexComplete'):t('hkexIncomplete')} · ${w.start} ≤ ${basis(w.basis)} < ${w.end} · ${t('hkexEndExclusive')}`;
    $('hkex-next').hidden=!nextCursor;$('hkex-message').textContent=result.data.length?'':t('hkexEmpty');$('hkex-list-heading').focus();
  }catch{if(turn===generation)$('hkex-message').textContent=t('hkexFailed');}
}
async function detail(serial){
  const turn=++generation;
  try{
    const result=await fetchJSON('browser/disclosures/'+encodeURIComponent(serial),{version});if(turn!==generation)return;
    const row=result.data;cache.set(serial,row);$('hkex-detail').hidden=false;$('hkex-detail-heading').textContent=`${serial} · ${subjectName(row)}`;
    $('hkex-dates').replaceChildren();
    for(const [key,value] of [['hkexState',t(states[row.state])],['hkexEvent',row.event_date.value],['hkexAware',row.aware_date?.value],['hkexFiled',row.filed_date.value],['hkexPublished',row.published_date.value],['hkexWithdrawn',row.withdrawn_date.value],['hkexObserved',row.capture.observed_at]])$('hkex-dates').append(text('dt',t(key)),text('dd',value??t('hkexUnknown')));
    const party=ref=>row.parties?.find(p=>p.ref===ref)?.disclosed_name??t('hkexUnknown');
    const security=id=>{const value=row.securities.find(s=>s.source_id===id);return value?`${value.name} · ${value.share_class??t('hkexUnknown')}`:t('hkexUnknown');};
    const code=(value,family)=>value==null?t('hkexUnknown'):[value,result.dictionaries?.[family]?.[value]].filter(Boolean).join(' · ');
    const wrap=text('div','');wrap.className='hkex-table';wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',t('hkexShares'));
    const table=document.createElement('table'),thead=document.createElement('thead'),tr=document.createElement('tr');
    for(const key of ['hkexInstrument','hkexSecurity','hkexRelatedParty','hkexPosition','hkexNature','hkexPhase','hkexCapacity','hkexShares','hkexPercent','hkexUnit'])tr.append(text('th',t(key)));
    thead.append(tr);table.append(thead);const tbody=document.createElement('tbody');
    for(const line of row.interests){const r=document.createElement('tr');for(const v of [label(line.instrument),security(line.security_id),party(line.party_ref),label(line.position),label(line.nature),label(line.phase),code(line.capacity_code,'capacity'),line.shares,line.percentage,line.unit])r.append(text('td',v));tbody.append(r);}
    table.append(tbody);wrap.append(table);$('hkex-interests').replaceChildren(wrap);
    const particulars=row.particulars||[];$('hkex-particulars').hidden=!particulars.length;
    const priceKinds={highest:'hkexHighestPrice',average:'hkexAveragePrice'};
    factualTable('hkex-particulars-table',['hkexReason','hkexPosition','hkexSecurity','hkexShares','hkexCapacityBefore','hkexCapacityAfter','hkexPrices'],particulars.map(p=>{
      const prices=p.prices?.length?p.prices:p.price==null?[]:[{kind:null,value:p.price,currency:p.currency,unit:p.unit}];
      return [code(p.reason_code,'reason'),label(p.position??'unknown'),security(p.security_id),p.shares,code(p.capacity_before,'capacity'),code(p.capacity_after,'capacity'),prices.length?prices.map(v=>`${priceKinds[v.kind]?t(priceKinds[v.kind]):t('hkexUnknown')}: ${v.value} ${v.currency??t('hkexUnknown')} · ${v.unit==='per_share'?t('hkexPerShare'):v.unit??t('hkexUnknown')}`).join('\n'):t('hkexUnknown')];
    }),'hkexParticulars');
    const controls=row.controls||[];$('hkex-controls').hidden=!controls.length;
    factualTable('hkex-controls-table',['hkexControlledParty','hkexControllingParty','hkexControlPercent','hkexDirectInterest'],controls.map(c=>[party(c.controlled_party_ref),party(c.controlling_party_ref),c.percentage_control,c.direct_interest==='yes'?t('hkexYes'):c.direct_interest==='no'?t('hkexNo'):t('hkexUnknown')]),'hkexControlLinks');
    $('hkex-revisions').replaceChildren(...(row.revision_links.length?row.revision_links.map(link=>{const target=link.older===serial?link.newer:link.older;return button(`${link.older} → ${link.newer}`,()=>detail(target));}):[text('p',t('hkexNoRevisions'))]));
    $('hkex-version').textContent=`${t('hkexVersion')}: ${result.version}`;$('hkex-detail-heading').focus();
  }catch{if(turn===generation)$('hkex-message').textContent=t('hkexFailed');}
}
$('hkex-retry').addEventListener('click',check);$('hkex-search').addEventListener('submit',search);$('hkex-next').addEventListener('click',()=>list(selection,nextCursor));
window.addEventListener('mhk:language',()=>{clearData();check();});check();
