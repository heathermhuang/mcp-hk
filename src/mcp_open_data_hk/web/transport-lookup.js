import {fetchPublicJson} from './http.js';
import {RequestFlow} from './playground-state.js';
import {node,button,safeLink} from './playground-views.js';

const endpoint='/api/v1/transport';
const t=(key,values)=>MhkI18n.t('bus'+key,values);
const name=record=>record?.[MhkI18n.locale==='zh-Hant'?'zhHant':'en']||record?.en||record?.zhHant;
const stopName=stop=>name(stop.name)||stop.stopId;
const date=value=>MhkI18n.date(value);
const epoch=value=>typeof value==='number'?value:Date.parse(value)/1000;
const stopIdentity=stop=>'td:stop:'+stop.stopId;
const isHeld=code=>/RESTRICTED|HELD|HOLD|BUDGET|ACCESS_DENIED/.test(code);
const isExpired=code=>/STALE|EXPIRED/.test(code);
const isTimeout=code=>/TIMEOUT|comparison_deadline/.test(code);

function liveRegion(){
  const box=node('p');
  box.setAttribute('role','status');
  return box;
}

function errorLabel(code){
  if(isTimeout(code))return t('Timeout');
  if(isExpired(code))return t('Expired');
  if(isHeld(code))return t('Held');
  return t('Failed');
}

async function read(flow,path,body,onData,onError,{live=false}={}){
  const run=flow.start();
  // A live comparison itself can take 45 seconds. Give it time to return partial results.
  const deadline=AbortSignal.timeout(live?60000:120000);
  try{
    const response=await fetchPublicJson(path,body,{
      signal:AbortSignal.any([run.signal,deadline]),
      attempts:live?1:3,
    });
    if(run.current())onData(response);
  }catch(error){
    if(run.current())onError(deadline.aborted?'SOURCE_TIMEOUT':error.code||'');
  }
}

function showSources(target,response){
  const details=node('details',null,'mhk-disclosure');
  details.append(node('summary',t('Sources')));
  const list=node('ul');
  if(response.meta?.indexVersion)list.append(node('li',t('Version',{version:response.meta.indexVersion})));
  const sources=new Set();
  for(const item of response.provenance||[]){
    const href=item.originalSourceUrl||item.originalResourceUrl||item.sourceUrl;
    if(!href||sources.has(href))continue;
    sources.add(href);
    const li=node('li');
    li.append(safeLink(href,item.attribution||href));
    for(const [key,value] of [['Modified',item.sourceModified],['Retrieved',item.retrievedAt],['Checked',item.lastCheckedAt]]){
      if(value!=null)li.append(node('div',t(key,{time:date(value)})));
    }
    list.append(li);
  }
  details.append(list);
  target.append(details);
}

function routeCard(route,direction,board,alight){
  const card=node('article',null,'pg-source-choice');
  const outbound=direction==='outbound',from=name(outbound?route.origin:route.destination),to=name(outbound?route.destination:route.origin);
  const routeName=[route.operator,route.route].filter(Boolean).join(' ');
  card.append(node('h4',routeName),node('p',[t(outbound?'Outbound':'Inbound'),from&&to?from+' → '+to:to].filter(Boolean).join(' · ')));
  if(board&&alight)card.append(node('p',stopName(board)+' → '+stopName(alight)));
  if(route.sourceUpdatedAt)card.append(node('p',t('Modified',{time:date(route.sourceUpdatedAt)}),'mhk-note'));
  if(route.specialType!=null&&route.specialType!=='0')card.append(node('p',t('Special',{code:route.specialType}),'mhk-note'));
  return card;
}

function stopPicker(key,choose,clear){
  const flow=new RequestFlow(),box=node('section',null,'pg-bus-picker'),status=liveRegion();
  const form=node('form'),label=node('label',t(key)),input=node('input'),submit=node('button',t('Search'),'mhk-button');
  input.type='search';input.required=true;input.maxLength=200;input.id='pg-bus-'+key.toLowerCase();label.htmlFor=input.id;
  form.append(label,input,submit);
  const matches=node('ul',null,'pg-bus-matches'),selection=node('div');
  box.append(form,status,matches,selection);
  const select=stop=>{
    form.hidden=true;matches.replaceChildren();status.textContent='';
    const change=button(t('Change'),()=>{
      clear();selection.replaceChildren();form.hidden=false;input.focus();
    });
    selection.append(node('p',t('Selected',{stop:stopName(stop),id:stop.stopId})),change);
    change.focus();
    choose(stop);
  };
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const query=input.value.trim();
    if(!query)return;
    matches.replaceChildren();status.textContent=t('Searching');
    const params=new URLSearchParams({q:query,limit:20});
    read(flow,endpoint+'/stops?'+params,null,response=>{
      const {items,totalMatched}=response.data;
      status.textContent=items.length?t('Choose',{shown:items.length,total:totalMatched}):t('NoStops');
      for(const stop of items){
        const location=Number.isFinite(stop.latitude)&&Number.isFinite(stop.longitude)
          ? stop.latitude.toFixed(5)+', '+stop.longitude.toFixed(5) : '';
        const details=[stopIdentity(stop),stop.operators?.join(' / '),location].filter(Boolean).join(' · ');
        const item=node('li');
        item.append(button(stopName(stop)+' · '+details,()=>select(stop)));
        matches.append(item);
      }
    },code=>{status.textContent=errorLabel(code);});
  });
  return {box,cancel:()=>flow.cancel()};
}

function showArrivals(card,candidate){
  const status=node('p');card.append(status);
  if(candidate.arrivalStatus==='ineligible'){
    status.textContent=t('WrongOrder');
    return null;
  }
  if(candidate.arrivalStatus!=='live'){
    const code=candidate.arrivalError?.code||candidate.uncheckedReason||'';
    const label=candidate.arrivalStatus==='unchecked'&&!isTimeout(code)?t('Unchecked'):errorLabel(code);
    status.textContent=code?label+' ('+code+')':label;
    return null;
  }
  const arrivals=candidate.arrivals,transport=arrivals?.transport,checked=candidate.arrivalCheckedAt;
  const prediction=candidate.earliestPredictedDeparture;
  const sourceCheck=epoch(arrivals?.provenance?.[0]?.lastCheckedAt);
  const cacheExpiry=(Number.isFinite(sourceCheck)?sourceCheck:epoch(checked))+(transport?.cacheTTLSeconds??20);
  const expiry=Math.min(transport?.freshUntil??cacheExpiry,cacheExpiry);
  const notes=node('div');
  if(checked)notes.append(node('p',t('Checked',{time:date(checked)}),'mhk-note'));
  for(const warning of arrivals?.warnings||[])if(warning.message)notes.append(node('p',warning.message,'mhk-note'));
  if(transport?.sourceTimestamp)notes.append(node('p',t('Observed',{time:date(transport.sourceTimestamp)}),'mhk-note'));
  showSources(notes,{provenance:[...(arrivals?.provenance||[]),...(candidate.operatorVerification?.provenance||[])]});
  card.append(notes);
  const update=()=>{
    if(!Number.isFinite(expiry)||expiry*1000<=Date.now()){status.textContent=t('Expired');return false;}
    const predictedAt=prediction?Date.parse(prediction):NaN;
    if(predictedAt>Date.now())status.textContent=t('Prediction',{time:date(prediction)});
    else if(prediction)status.textContent=t('Expired');
    else status.textContent=arrivals?.items?.length?t('NoFuture'):t('NoPredictions');
    return true;
  };
  update();
  return update;
}

export function mountTransport(target,browse){
  const routesFlow=new RequestFlow(),journeyFlow=new RequestFlow();
  const routes=node('section'),reference=node('section'),live=node('section');
  const routesStatus=liveRegion(),journeyStatus=liveRegion(),liveStatus=liveRegion();
  const find=button(t('Find'),()=>findJourneys(false));
  const check=button(t('Check'),()=>findJourneys(true));
  check.hidden=true;find.disabled=true;
  const result=node('div'),liveResult=node('div');
  let origin,destination,timer;
  const resetJourney=()=>{
    journeyFlow.cancel();clearInterval(timer);
    journeyStatus.textContent=liveStatus.textContent='';
    result.replaceChildren();liveResult.replaceChildren();
    check.hidden=true;check.disabled=false;find.disabled=!origin||!destination;
  };
  const setOrigin=stop=>{
    origin=stop;resetJourney();routes.replaceChildren();
    routesFlow.cancel();routesStatus.textContent='';
    if(!stop)return;
    routesStatus.textContent=t('ReadingRoutes');
    read(routesFlow,endpoint+'/stops/'+encodeURIComponent(stop.stopId)+'/routes',null,response=>{
      const {items}=response.data;
      routesStatus.textContent=items.length?t('RouteCount',{count:items.length}):t('NoRoutes');
      if(response.provenance?.some(source=>source.stale))routes.append(node('p',t('ReferenceStale'),'mhk-note'));
      for(const row of items)routes.append(routeCard(row,row.direction));
      showSources(routes,response);
    },code=>{routesStatus.textContent=errorLabel(code);});
  };
  const setDestination=stop=>{destination=stop;resetJourney();};
  const originPicker=stopPicker('Origin',setOrigin,()=>setOrigin(null));
  const destinationPicker=stopPicker('Destination',setDestination,()=>setDestination(null));
  const catalogue=button(t('Catalogue'),browse);
  reference.append(find,journeyStatus,result);
  live.append(check,liveStatus,liveResult);
  target.replaceChildren(node('p',t('Scope')),originPicker.box,destinationPicker.box,reference,live,
    node('h3',t('Routes')),routesStatus,routes,catalogue);

  function findJourneys(includeArrivals){
    if(!origin||!destination)return;
    if(origin.stopId===destination.stopId){journeyStatus.textContent=t('SameStop');return;}
    clearInterval(timer);
    const status=includeArrivals?liveStatus:journeyStatus;
    const output=includeArrivals?liveResult:result;
    output.replaceChildren();
    if(!includeArrivals){
      liveStatus.textContent='';liveResult.replaceChildren();check.hidden=true;
    }
    find.disabled=true;check.disabled=true;
    const restoreButtons=()=>{find.disabled=false;check.disabled=false;};
    status.textContent=t(includeArrivals?'Checking':'ReadingRoutes');
    read(journeyFlow,endpoint+'/journeys',{
      origin:stopIdentity(origin),destination:stopIdentity(destination),includeArrivals,limit:5,
    },response=>{
      restoreButtons();
      const data=response.data,coverage=data.coverage;
      const originMatches=data.originCandidates?.map(stop=>stop.stopId);
      const destinationMatches=data.destinationCandidates?.map(stop=>stop.stopId);
      if(originMatches?.length!==1||originMatches[0]!==origin.stopId||
        destinationMatches?.length!==1||destinationMatches[0]!==destination.stopId){
        status.textContent=t('SelectionExpired');check.hidden=true;return;
      }
      if(!includeArrivals){
        status.textContent=data.items.length?t('ReferenceCount',{shown:data.items.length,total:data.referenceCandidateCount}):t('NoDirect');
        check.hidden=!data.items.length;
      }else{
        status.textContent=t('Coverage',{
          shown:data.items.length,total:data.totalDepartureChoices,accepted:coverage.acceptedArrivalChecks,
          failed:coverage.failed,unchecked:coverage.unchecked,ineligible:coverage.verifiedNotServingOrder,
        });
        if(!coverage.complete)output.append(node('p',t('Partial'),'mhk-note'));
        if(coverage.uncheckedReasons?.comparison_deadline)output.append(node('p',t('Timeout'),'mhk-note'));
      }
      if(coverage?.referenceIndexStale)output.append(node('p',t('ReferenceStale'),'mhk-note'));
      const updates=[];
      for(const row of data.items){
        const card=routeCard(row.route,row.direction,row.board,row.alight);
        if(includeArrivals){
          const update=showArrivals(card,row);
          if(update)updates.push(update);
        }
        output.append(card);
      }
      showSources(output,response);
      if(updates.length)timer=setInterval(()=>{if(!updates.map(update=>update()).some(Boolean))clearInterval(timer);},1000);
    },code=>{
      restoreButtons();status.textContent=errorLabel(code);
    },{live:includeArrivals});
  }
  return {dispose(){
    originPicker.cancel();destinationPicker.cancel();routesFlow.cancel();journeyFlow.cancel();
    clearInterval(timer);target.replaceChildren();
  }};
}
