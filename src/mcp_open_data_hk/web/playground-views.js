export const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
export const button=(text,fn)=>{const n=node('button',text,'mhk-button mhk-secondary');n.type='button';n.addEventListener('click',fn);return n;};
export function safeLink(value,text){try{const u=new URL(value);if(!['https:','http:'].includes(u.protocol)||u.username||u.password)return node('span',text);const a=node('a',text);a.href=u.href;a.rel='noreferrer';return a;}catch{return node('span',text);}}
export function cellText(cell,locale='en',calendar=false){
  if(cell.kind==='missing')return '— (missing)';
  if(cell.kind==='null')return 'null';
  if(cell.kind==='json'){try{if(calendar){const value=JSON.parse(cell.json);if(Array.isArray(value)&&value[1]?.value==='DATE'&&/^\d{8}$/.test(value[0]))return value[0].slice(0,4)+'-'+value[0].slice(4,6)+'-'+value[0].slice(6,8);}const value=JSON.parse(cell.json);if(value&&typeof value==='object'&&!Array.isArray(value)){const name=locale==='zh-Hant'?value.zhHant||value.nameZhHant||value.name:value.en||value.name; if(typeof name==='string')return name;}}catch{/* Show original source text. */}return '…';}
  return cell.text;
}
export function drawChart(target,p,view,t){
  target.replaceChildren();
  const label=p.columns.indexOf(view.label),measure=p.columns.indexOf(view.measure);
  if(label<0||measure<0||!view.unit?.trim())throw Error('INVALID_CHART');
  const values=p.rows.map(r=>{const cell=r[measure],n=Number(cell.text);if(!['integer','float'].includes(cell.kind)||!Number.isFinite(n)||Math.abs(n)>Number.MAX_SAFE_INTEGER||cell.kind==='float'&&String(n).replace(/\.0$/,'')!==cell.text.replace(/\.0$/,''))throw Error('INVALID_CHART');return n;});
  const extent=Math.max(1,...values.map(Math.abs));
  target.append(node('p',t('Scope')+' · '+view.unit));
  const list=node('div');list.setAttribute('role','list');
  values.forEach((value,i)=>{const row=node('div',null,'pg-bar');row.setAttribute('role','listitem');row.append(node('span',cellText(p.rows[i][label])));const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 200 20');svg.setAttribute('aria-hidden','true');const rect=document.createElementNS(svg.namespaceURI,'rect');rect.setAttribute('x',value<0?String(100-100*Math.abs(value)/extent):'100');rect.setAttribute('y','1');rect.setAttribute('width',String(100*Math.abs(value)/extent));rect.setAttribute('height','18');if(value<0)rect.setAttribute('class','pg-bar-negative');svg.append(rect);row.append(svg,node('span',p.rows[i][measure].text+' '+view.unit));list.append(row);});
  target.append(list); // The same records and exact measures remain accessible as the native table.
}
export function drawLocations(target,rows,t){
  target.replaceChildren();const points=rows.filter(r=>typeof r.longitude==='number'&&typeof r.latitude==='number'&&Number.isFinite(r.longitude)&&Number.isFinite(r.latitude)&&r.longitude>=113.8&&r.longitude<=114.6&&r.latitude>=22.1&&r.latitude<=22.6);
  if(!points.length)return;
  target.append(node('p',t('Map')),node('p',t('MapMissing',{n:rows.length-points.length}),'mhk-note'));
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 480 240');svg.setAttribute('role','img');svg.setAttribute('aria-label',t('Map'));
  const axes=document.createElementNS(svg.namespaceURI,'text');axes.setAttribute('x','10');axes.setAttribute('y','230');axes.textContent='113.8° E → 114.6° E · 22.1° N ↑ 22.6° N';svg.append(axes);
  points.forEach(r=>{const circle=document.createElementNS(svg.namespaceURI,'circle');circle.setAttribute('class','pg-map-point');circle.setAttribute('cx',String(20+(r.longitude-113.8)/.8*440));circle.setAttribute('cy',String(210-(r.latitude-22.1)/.5*190));circle.setAttribute('r','4');const title=document.createElementNS(svg.namespaceURI,'title');title.textContent=r.id+' · '+r.longitude+', '+r.latitude;circle.append(title);svg.append(circle);});target.append(svg);
}
