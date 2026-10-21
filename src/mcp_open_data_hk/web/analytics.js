/* Basic consent: no Google request, cookie or ping before an affirmative choice. */
(() => {
  const key = 'mhk-analytics-choice', maxAge = 180 * 86400000;
  const production = location.hostname === 'mcp.hk' && location.protocol === 'https:';
  let id = '', loaded = false, choice = null, lastPath = null;
  const denied = {analytics_storage:'denied',ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied'};
  const respectsOptOut = () => navigator.globalPrivacyControl === true || navigator.doNotTrack === '1';
  try { const stored = JSON.parse(localStorage.getItem(key)); if (stored?.version === 1 && typeof stored.allowed === 'boolean' && Date.now()-stored.at >= 0 && Date.now()-stored.at < maxAge) choice = stored; } catch { /* Storage is optional. */ }
  const t = name => window.MhkI18n?.t(name) || name;
  const dialog = document.createElement('dialog'); dialog.id = 'mhk-privacy-choice'; dialog.setAttribute('aria-labelledby','mhk-consent-title');
  const title = document.createElement('h2'); title.id='mhk-consent-title';
  const copy = document.createElement('p'), status = document.createElement('p'), privacy = document.createElement('a'), reject = document.createElement('button'), accept = document.createElement('button'), close = document.createElement('button');
  privacy.href='/privacy'; reject.type=accept.type=close.type='button';
  dialog.append(title,copy,status,privacy,reject,accept,close); document.body.append(dialog);
  function render() {
    title.textContent=t('analyticsChoiceTitle'); copy.textContent=t('analyticsChoiceCopy'); privacy.textContent=t('privacyTitle');
    reject.textContent=t('analyticsReject'); accept.textContent=t('analyticsAllow'); close.textContent=t('close');
    accept.disabled=!id || !production || respectsOptOut();
    status.textContent=t(respectsOptOut() ? 'analyticsOptOut' : !id || !production ? 'analyticsNotConfigured' : choice?.allowed ? 'analyticsEnabled' : 'analyticsDisabled');
  }
  function removeCookies() {
    for (const part of document.cookie.split(';')) {
      const name=part.trim().split('=')[0];
      if (!/^_ga(?:_|$)/.test(name)) continue;
      for (const domain of ['', '; domain=mcp.hk', '; domain=.mcp.hk']) document.cookie=`${name}=; Max-Age=0; path=/; SameSite=Lax; Secure${domain}`;
    }
  }
  function start() {
    if (loaded || !production || !id || !choice?.allowed || respectsOptOut()) return;
    loaded=true; window['ga-disable-'+id]=false; window.dataLayer=window.dataLayer || [];
    window.gtag=function(){window.dataLayer.push(arguments);};
    window.gtag('consent','default',denied);
    window.gtag('consent','update',{...denied,analytics_storage:'granted'});
    window.gtag('js',new Date());
    const safeLocation=location.origin+location.pathname;
    window.gtag('set',{page_location:safeLocation,page_referrer:'',page_title:'mcp.hk',ignore_referrer:true});
    window.gtag('config',id,{send_page_view:false,page_location:safeLocation,page_referrer:'',page_title:'mcp.hk',allow_google_signals:false,allow_ad_personalization_signals:false,cookie_expires:15552000});
    pageView();
    const script=document.createElement('script'); script.async=true; script.src='https://www.googletagmanager.com/gtag/js?id='+id; document.head.append(script);
  }
  function pageView() {
    if (!loaded || !choice?.allowed || respectsOptOut() || lastPath === location.pathname) return;
    lastPath=location.pathname;
    window.gtag('event','page_view',{send_to:id,page_location:location.origin+location.pathname,page_referrer:'',page_title:'mcp.hk'});
  }
  function choose(allowed) {
    choice={version:1,allowed,at:Date.now()};
    try {localStorage.setItem(key,JSON.stringify(choice));} catch { /* Choice still applies to this page. */ }
    if (allowed) start();
    else { if (id) window['ga-disable-'+id]=true; removeCookies(); }
    dialog.close(); render();
    if (!allowed && loaded) location.reload();
  }
  reject.addEventListener('click',()=>choose(false)); accept.addEventListener('click',()=>choose(true)); close.addEventListener('click',()=>dialog.close());
  document.querySelectorAll('[data-analytics-settings]').forEach(button=>button.addEventListener('click',()=>{render();if(dialog.open)dialog.close();dialog.showModal();}));
  window.addEventListener('mhk:language',render);
  window.addEventListener('mhk:navigate',pageView);window.addEventListener('popstate',pageView);
  render();
  if (production) fetch('/assets/site-config.json',{cache:'no-store'}).then(r=>r.ok?r.json():{}).then(config=>{
    id=/^G-[A-Z0-9]{4,20}$/.test(config.googleAnalyticsId || '') ? config.googleAnalyticsId : '';
    render();
    if (respectsOptOut()) { if(id)window['ga-disable-'+id]=true;removeCookies();return; }
    if (choice?.allowed) start(); else if (id && !choice && !dialog.open) dialog.show();
  }).catch(()=>{/* Optional analytics never prevents use of the service. */});
})();
