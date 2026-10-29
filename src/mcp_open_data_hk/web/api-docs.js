/* Runtime OpenAPI is the contract. This page never queries source records on load. */
(() => {
  if(!globalThis.MhkI18n)return; // A saved-locale redirect may be replacing this document.
  const $=id=>document.getElementById(id),t=(...a)=>MhkI18n.t(...a),methods=new Set(['get','post','put','patch','delete','head','options','trace']);
  const groupKeys={catalogue:'docsGroupCatalogue',companies:'docsGroupCompanies',disclosures:'docsGroupDisclosures',places:'docsGroupPlaces',plates:'docsGroupPlates',properties:'docsGroupProperties',racing:'docsGroupRacing',resources:'docsGroupResources',sfc:'docsGroupSfc',service:'docsGroupService'};
  const node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  let spec=null,labels={},families=[],entries=[],consoleUi=null,consoleLoading=false,loading=false,timer;
  const params=new URL(location.href).searchParams;let query=(params.get('q')||'').slice(0,200),selectedGroup=params.get('group')||'';
  $('docs-query').value=query;
  const normal=value=>String(value).normalize('NFKC').toLowerCase();
  const title=entry=>labels[entry.key]?.[MhkI18n.locale]||entry.operation.summary||entry.path;
  function groupFor(path){const root=path.split('/')[3];if(path.startsWith('/api/v1/catalogue')||root==='datasets')return 'catalogue';if(['addresses','restaurants','districts'].includes(root))return 'places';if(root==='hkex')return 'disclosures';return ['companies','plates','properties','racing','resources','sfc'].includes(root)?root:'service';}
  const familyIds={addresses:['addresses'],restaurants:['restaurants'],districts:['population'],plates:['platehk'],properties:['seehouse'],companies:['company_registry','enigma','sfc_archive'],hkex:['hkex_daily','webb_sdi'],racing:['racing'],sfc:['sfc_archive'],catalogue:['catalogue','transport'],datasets:['catalogue'],resources:['catalogue','transport']};
  function aliases(entry){const ids=familyIds[entry.path.split('/')[3]]||[];return families.filter(f=>ids.includes(f.id)).map(f=>[f.keywords,...Object.values(f.title),...Object.values(f.question)].join(' ')).join(' ');}
  function sync(){const u=new URL(location.href);for(const [k,v]of [['q',query],['group',selectedGroup]]){if(v)u.searchParams.set(k,v);else u.searchParams.delete(k);}history.replaceState(null,'',u.pathname+u.search+u.hash);}
  function resolve(value){if(!value?.$ref?.startsWith('#/'))return value;return value.$ref.slice(2).split('/').reduce((v,k)=>v?.[k.replace(/~1/g,'/').replace(/~0/g,'~')],spec)||value;}
  function schemaView(value,seen=[]){
    if(Array.isArray(value))return value.map(v=>schemaView(v,seen));
    if(!value||typeof value!=='object')return value;
    if(value.$ref&&!seen.includes(value.$ref)&&seen.length<16){
      const target=resolve(value);if(target!==value){const {$ref,...siblings}=value;return {...schemaView(target,[...seen,$ref]),...schemaView(siblings,[...seen,$ref])};}
    }
    return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,schemaView(v,seen)]));
  }
  function code(value){const e=node('pre',JSON.stringify(value,null,2));e.tabIndex=0;return e;}
  function schemaSummary(value){
    const s=resolve(value)||{},parts=[];
    if(s.type)parts.push(Array.isArray(s.type)?s.type.join(' | '):s.type+(s.items?.type?'<'+s.items.type+'>':''));
    for(const key of ['format','enum','default','minimum','maximum','minLength','maxLength','minItems','maxItems','maxProperties','pattern','anyOf','oneOf'])if(key in s)parts.push(key+'='+JSON.stringify(s[key]));
    return parts.join(' · ')||JSON.stringify(s);
  }
  function parameterTable(parameters,withLocation=true){
    const wrap=node('div','');wrap.className='docs-table-wrap';wrap.tabIndex=0;wrap.setAttribute('aria-label',t('docsParameters'));
    const table=node('table',''),head=node('thead',''),hr=node('tr','');
    for(const key of ['docsName',...(withLocation?['docsLocation']:[]),'docsRequired','docsType']){const th=node('th',t(key));th.scope='col';hr.append(th);}head.append(hr);table.append(head);
    const tbody=node('tbody','');for(const p of parameters){const tr=node('tr','');tr.append(node('td',p.name));if(withLocation)tr.append(node('td',p.in));tr.append(node('td',t(p.required?'docsRequired':'docsOptional')));const cell=node('td','');cell.append(node('code',schemaSummary(p.schema)));tr.append(cell);tbody.append(tr);}table.append(tbody);wrap.append(table);return wrap;
  }
  function operationId(entry){return 'operation-'+encodeURIComponent(entry.key);}
  function renderOperation(entry){
    const row=node('details','');row.className='docs-operation';row.id=operationId(entry);
    const summary=node('summary',''),method=node('span',entry.method.toUpperCase()),path=node('code',entry.path),name=node('span',title(entry));method.className='docs-method';name.className='docs-operation-name';summary.append(method,path,name);row.append(summary);
    const body=node('div','');body.className='docs-operation-body';
    const link=node('a',t('docsOperationLink')+' ↗');link.href='#'+row.id;body.append(link);
    body.append(node('h4',t('docsParameters')));
    const parameters=[...new Map([...(entry.pathItem.parameters||[]),...(entry.operation.parameters||[])].map(resolve).map(p=>[p.in+' '+p.name,p])).values()];
    if(!parameters.length)body.append(node('p',t('docsNoParameters')));
    else body.append(parameterTable(parameters));
    if(entry.operation.requestBody){
      const request=resolve(entry.operation.requestBody);body.append(node('h4',t('docsRequestBody')));
      for(const [media,definition]of Object.entries(request.content||{})){
        body.append(node('p',media+' · '+t(request.required?'docsRequired':'docsOptional')));const schema=schemaView(definition.schema||{});
        if(schema.properties)body.append(parameterTable(Object.entries(schema.properties).map(([name,value])=>({name,required:(schema.required||[]).includes(name),schema:value})),false));
      }
      const definition=node('details','');definition.append(node('summary','JSON Schema'),code(schemaView(request)));body.append(definition);
    }
    body.append(node('h4',t('docsResponses')));const responses=node('div','');responses.className='docs-responses';
    for(const [status,response]of Object.entries(entry.operation.responses||{})){const d=node('details','');d.append(node('summary',status),code(schemaView(response)));responses.append(d);}body.append(responses);
    const raw=node('details','');raw.className='docs-raw';raw.append(node('summary',t('docsRaw')),code(entry.operation));body.append(raw);row.append(body);
    row.addEventListener('toggle',()=>{if(!row.isConnected)return;const u=new URL(location.href);if(row.open)u.hash=row.id;else if(u.hash==='#'+row.id)u.hash='';history.replaceState(null,'',u.pathname+u.search+u.hash);});
    return row;
  }
  function render(revealHash=false){
    document.title=t('apiReferenceTitle')+' · mcp.hk';if(!spec)return;
    const groups=[...new Set(entries.map(e=>e.group))].sort((a,b)=>translations.en[groupKeys[a]].localeCompare(translations.en[groupKeys[b]],'en'));
    $('docs-group').replaceChildren(new Option(t('docsAllGroups'),''),...groups.map(g=>new Option(t(groupKeys[g]),g)));
    if(!groups.includes(selectedGroup))selectedGroup='';$('docs-group').value=selectedGroup;
    const words=normal(query).split(/\s+/).filter(Boolean),method=methods.has(words[0])?words.shift():null;
    const visible=entries.filter(e=>(!method||e.method===method)&&(!selectedGroup||e.group===selectedGroup)&&words.every(word=>normal([e.key,aliases(e),e.operation.operationId,e.operation.summary,e.operation.description,...(e.operation.tags||[]),labels[e.key]?.en,labels[e.key]?.['zh-Hant'],translations.en[groupKeys[e.group]],translations.zh[groupKeys[e.group]]].join(' ')).includes(word)));
    $('docs-status').textContent=t('docsCount',{shown:visible.length,total:entries.length});$('docs-clear').hidden=!(query||selectedGroup);$('docs-operations').replaceChildren();
    if(!visible.length){$('docs-operations').append(node('p',t('docsEmpty')));return;}
    let target=null;
    for(const group of groups){const matches=visible.filter(e=>e.group===group);if(!matches.length)continue;
      const section=node('details','');section.className='docs-group';const summary=node('summary','');summary.append(node('h3',t(groupKeys[group])),node('span',String(matches.length)));section.append(summary);
      for(const entry of matches){const row=renderOperation(entry);if(location.hash==='#'+row.id){row.open=true;target=row;}section.append(row);}
      section.open=Boolean(query||selectedGroup||target&&section.contains(target));$('docs-operations').append(section);
    }
    if(target&&revealHash)target.scrollIntoView({block:'start'});
  }
  const consoleAssets=new Map();
  function consoleAsset(src,tag){
    if(!consoleAssets.has(src))consoleAssets.set(src,new Promise((resolve,reject)=>{
      const e=document.createElement(tag);if(tag==='script')e.src=src;else{e.rel='stylesheet';e.href=src;}
      e.onload=resolve;e.onerror=()=>{consoleAssets.delete(src);e.remove();reject(Error('Console asset unavailable'));};document.head.append(e);
    }));
    return consoleAssets.get(src);
  }
  async function consoleReference(){
    if(!spec||consoleUi||consoleLoading||!$('docs-console').open)return;
    consoleLoading=true;
    try{
      await Promise.all([consoleAsset('/assets/swagger-ui-bundle.js','script'),consoleAsset('/assets/swagger-ui.css','link')]);
      consoleUi=SwaggerUIBundle({spec,dom_id:'#swagger-ui',layout:'BaseLayout',deepLinking:true,docExpansion:'none',showExtensions:true,showCommonExtensions:true,validatorUrl:null,presets:[SwaggerUIBundle.presets.apis]});
    }catch{
      $('swagger-ui').replaceChildren(node('p',t('docsConsoleError')));const retry=node('button',t('docsConsoleRetry'));retry.type='button';retry.className='mhk-button mhk-secondary';retry.addEventListener('click',consoleReference);$('swagger-ui').append(retry);
    }
    finally{consoleLoading=false;}
  }
  async function load(){
    if(loading)return;loading=true;$('docs-retry').hidden=true;$('docs-status').textContent=t('apiReferenceLoading');$('docs-query').disabled=true;$('docs-group').disabled=true;
    try{
      const responses=await Promise.all([fetch('/openapi.json'),fetch('/assets/api-docs-labels.json'),fetch('/assets/datasets.json')]);if(responses.some(r=>!r.ok))throw Error('Schema unavailable');
      const [schema,copy,registry]=await Promise.all(responses.map(r=>r.json()));if(!schema.paths||typeof schema.paths!=='object'||!copy||typeof copy!=='object'||!Array.isArray(registry))throw Error('Invalid schema');
      const next=[];for(const [path,item]of Object.entries(schema.paths))for(const [method,operation]of Object.entries(item))if(methods.has(method))next.push({key:method.toUpperCase()+' '+path,path,pathItem:item,method,operation,group:groupFor(path)});
      spec=schema;labels=copy;families=registry;entries=next.sort((a,b)=>a.path.localeCompare(b.path,'en')||a.method.localeCompare(b.method,'en'));$('docs-query').disabled=false;$('docs-group').disabled=false;render(true);
      if(location.hash.startsWith('#/'))$('docs-console').open=true;consoleReference();
    }catch{$('docs-status').textContent=t('docsUnavailable');$('docs-retry').hidden=false;$('docs-operations').replaceChildren();}
    finally{loading=false;}
  }
  function search(){clearTimeout(timer);query=$('docs-query').value.trim();sync();render();}
  $('docs-search').addEventListener('submit',e=>{e.preventDefault();search();});$('docs-query').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(search,150);});
  $('docs-group').addEventListener('change',()=>{selectedGroup=$('docs-group').value;search();});
  $('docs-clear').addEventListener('click',()=>{query='';selectedGroup='';$('docs-query').value='';sync();render();$('docs-query').focus();});
  $('docs-retry').addEventListener('click',load);$('docs-console').addEventListener('toggle',consoleReference);
  $('docs-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('docs-first-code').textContent);$('docs-copy-status').textContent=t('docsCopied');}catch{$('docs-copy-status').textContent=t('docsCopyFailed');$('docs-first-code').focus();}});
  window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#/')){$('docs-console').open=true;consoleReference();}else render(true);});
  window.addEventListener('mhk:language',render);load();
})();
