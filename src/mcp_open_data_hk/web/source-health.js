/* Public accepted-state metadata only. No collection, polling or all-family fan-out. */
import {fetchPublicJson} from './http.js';
const endpoints={hkex_daily:'/api/v1/hkex/latest/status',company_registry:'/api/v1/companies/updates/status',seehouse:'/api/v1/properties/coverage',racing:'/api/v1/racing/status',sfc_archive:'/api/v1/sfc/status',restaurants:'/api/v1/status',population:'/api/v1/status',addresses:'/api/v1/status'};
export function healthSummary(family,payload,locale='en'){
  const zh=locale==='zh-Hant',pick=(en,cn)=>zh?cn:en,unknown=pick('Unknown','未知');
  const n=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString(zh?'zh-HK':'en-HK'):unknown;
  const pair=(a,b)=>`${n(a)} / ${n(b)}`;
  const data=payload?.data||payload||{},facts=[],warnings=[];
  if(family==='hkex_daily'){
    facts.push([pick('Latest accepted summary','最新已接納摘要'),data.coverage?.latestSummaryDate||unknown],[pick('Last successful source read','上次成功讀取來源'),data.updater?.lastSuccessfulRead||unknown],[pick('Last status check','上次狀態檢查'),data.updater?.lastChecked||unknown]);
    if(data.updater?.holdCode||data.updater?.lastRun?.state==='failed')warnings.push(pick('Source updates are on hold or failed. Retained summaries remain available; newer filings may be missing.','來源更新暫停或失敗。保留的摘要仍可查閱，但可能缺少較新的披露。'));
    warnings.push(pick('Published summaries and the historical Webb archive have separate dates and coverage. These records do not establish current holdings.','已發布摘要與 Webb 歷史檔案的日期及涵蓋範圍不同；這些紀錄並非目前持股核實。'));
  }else if(family==='company_registry'){
    const c=data.coverage||{},q=data.maintenance?.addressQueue,capacity=q?.capacity;
    facts.push([pick('Published weekly files / discovered files','已發布每週檔案／已發現檔案'),pair(c.acceptedWeeklyFiles,c.discoveredWeeklyFiles)],[pick('Company records covered through','公司紀錄涵蓋至'),c.latestAcceptedCoverageEnd||unknown],[pick('Published address coverage / eligible companies','已發布地址涵蓋／合資格公司'),pair(c.addressEntities,c.addressEligibleObservedEntities)]);
    if(q)facts.push([pick('Successfully checked addresses in the collection queue (may be unpublished)','收集佇列中成功檢查的地址（可能尚未發布）'),n(q.observed)]);
    if(capacity?.wholeSubset90DayCycleFeasible===false){facts.push([pick('Minimum days for one whole-subset pass at the current cap','按目前上限完成一次全子集檢查最少日數'),n(capacity.fullPassMinimumDaysAtCurrentCap)]);warnings.push(pick('A complete 90-day address cycle is not feasible at the current quota. The refresh target applies to observed and explicitly tracked priority cohorts, subject to capacity.','目前配額無法在 90 天內完成全體地址檢查。更新目標只適用於已觀察及明確追蹤的優先群組，並受容量限制。'));}
    warnings.push(pick('This is an observed subset, not a complete current company register. No match does not establish dissolution.','這是觀察所得子集，並非完整的目前公司名冊；查無紀錄不代表公司已解散。'));
  }else if(family==='seehouse'){
    const c=data.productionCoverage,t=c?.totals||{};
    facts.push([pick('Coverage report computed','涵蓋報告計算時間'),c?.computedAt||data.generatedAt||unknown],[pick('Fresh / all listing observations','新鮮／全部放盤觀察'),pair(t.freshListings,t.activeSourceListings)],[pick('Aging listing observations','漸舊放盤觀察'),n(t.agingListings)],[pick('Stale listing observations','過時放盤觀察'),n(t.staleListings)],[pick('Unmatched listing observations','未配對放盤觀察'),n(t.unmatchedSourceListings)]);
    warnings.push(pick('The default view shows observations within 48 hours with building matches. A recent observation does not verify availability. Asking prices are not completed transactions.','預設只顯示 48 小時內觀察且已配對大廈的放盤。近期觀察並不核實供應狀態；叫價並非成交價。'));
  }else if(family==='racing'){
    const c=data.coverage||{},d=data.dividendCoverage||{};
    facts.push([pick('Accepted meetings','已接納賽馬日'),n(c.meetings)],[pick('Accepted races','已接納賽事'),n(c.races)],[pick('Accepted results date range','已接納賽果日期範圍'),`${c.earliest||unknown} → ${c.latest||unknown}`],[pick('Races with observed dividends / accepted races','有派彩觀察／已接納賽事'),pair(d.observedRaces,c.races)]);
    if(data.seasonCoverage?.some(s=>s.seasonComplete===false))warnings.push(pick('Season history is incomplete. Missing meetings and dividend quotes do not establish no racing or no payout.','馬季歷史尚未完整；缺少賽馬日或派彩紀錄並不代表沒有賽事或派彩。'));
    if(d.stakeNormalized===false)warnings.push(pick('Dividend quotes retain their source stake basis; they are not normalized returns.','派彩報價保留來源投注基準，並非標準化回報。'));
  }else if(family==='sfc_archive'){
    facts.push([pick('Official verification capability','官方核實功能'),data.state?(data.enabledModes?.includes('browser')?pick('Activated','已啟用'):pick('Not activated','未啟用')):unknown],[pick('Accepted official cohort','已接納官方群組'),n(data.cohort?.accepted)]);
    if(!data.enabledModes?.includes('browser'))warnings.push(pick('Official browser verification is not activated. The historical Webb licence archive remains separate.','官方網頁核實功能尚未啟用；Webb 牌照歷史檔案另行提供。'));
  }else{
    const s=data.sources?.find(s=>s.sourceId===family);
    if(s){facts.push([pick('Last successful source read','上次成功讀取來源'),s.lastSuccess||unknown],[pick('Accepted records','已接納紀錄'),n(s.recordCount)]);if(s.stale||s.refreshHealth?.overdue||s.refreshHealth?.latestAttemptFailed)warnings.push(pick('Source refresh is overdue or failed. Accepted records may be retained.','來源更新逾期或失敗，可能正提供保留的已接納紀錄。'));if(s.quality)facts.push([pick('Source records missing names in both languages','來源中英名稱均缺漏的紀錄'),n(s.quality.sourceNamesMissingBothLanguages)]);}
  }
  return {facts,warnings};
}
export class SourceHealth{
  constructor(target,locale=()=>MhkI18n.locale){this.target=target;this.locale=locale;this.sequence=0;}
  clear(){this.sequence++;this.controller?.abort();this.payload=null;this.family=null;this.target.replaceChildren();this.target.hidden=true;}
  async show(family){
    this.clear();const path=endpoints[family];if(!path)return;
    this.family=family;this.target.hidden=false;this.failed=false;this.render();const token=this.sequence;this.controller=new AbortController();
    try{const data=await fetchPublicJson(path,undefined,{signal:this.controller.signal});if(token!==this.sequence)return;this.payload=data;}
    catch(error){if(token!==this.sequence||error.name==='AbortError')return;this.failed=true;}
    if(token===this.sequence)this.render();
  }
  render(){
    if(!this.family)return;const zh=this.locale()==='zh-Hant',target=this.target;target.replaceChildren();
    const title=document.createElement('h3');title.textContent=zh?'目前涵蓋範圍及來源更新':'Current coverage and source updates';target.append(title);
    if(!this.payload){const p=document.createElement('p');p.textContent=this.failed?(zh?'無法讀取來源狀態。新鮮度未知；資料查詢仍可使用。':'Source status could not be read. Freshness is unknown; record queries remain available.'):(zh?'正在檢查已接納來源的狀態…':'Checking accepted source status…');target.append(p);return;}
    const {facts,warnings}=healthSummary(this.family,this.payload,this.locale()),dl=document.createElement('dl');dl.className='pg-source-facts';
    for(const [label,value]of facts){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=/^\d{4}-\d{2}-\d{2}T/.test(value)?MhkI18n.date(value):value;dl.append(dt,dd);}target.append(dl);
    for(const message of warnings){const p=document.createElement('p');p.className='mhk-note';p.textContent=message;target.append(p);}
  }
}
