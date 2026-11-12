/* Runs before data scripts. Only an explicit refusal is mirrored to the server. */
(() => {
  const production=location.hostname==='mcp.hk'&&location.protocol==='https:';
  function refused(){
    if(navigator.globalPrivacyControl===true||navigator.doNotTrack==='1')return true;
    try {const choice=JSON.parse(localStorage.getItem('mhk-analytics-choice'));return choice?.version===1&&choice.allowed===false;}catch{return false;}
  }
  function sync(allowed){
    if(!production)return;
    const off=allowed===false||navigator.globalPrivacyControl===true||navigator.doNotTrack==='1'||allowed===undefined&&refused();
    document.cookie='__Host-mhk_analytics='+(off?'off; Max-Age=31536000':'; Max-Age=0')+'; Path=/; Secure; SameSite=Lax';
  }
  window.MhkPrivacy={sync,headers:()=>refused()?{'x-mcp-analytics-opt-out':'1'}:{}};
  sync();window.addEventListener('storage',()=>sync());
})();
