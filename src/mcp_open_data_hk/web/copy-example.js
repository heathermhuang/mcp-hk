/* Copy only checked-in example text. Keep a keyboard fallback on restricted browsers. */
(() => {
  function attach(pre){
    const button=document.createElement('button');
    button.type='button';
    button.className='mhk-button mhk-secondary';
    button.textContent=MhkI18n.t('copyExample');
    const status=document.createElement('span');
    status.setAttribute('role','status');
    const controls=document.createElement('div');
    controls.className='mhk-example-actions';
    controls.append(button,status);
    pre.before(controls);
    button.addEventListener('click',async()=>{
      try{
        await navigator.clipboard.writeText(pre.textContent);
        status.textContent=MhkI18n.t('copyExampleReady');
      }catch{
        pre.focus();window.getSelection()?.selectAllChildren(pre);
        status.textContent=MhkI18n.t('copyExampleManual');
      }
    });
  }
  window.MhkCopyExample=attach;
  document.querySelectorAll('[data-copy-example]').forEach(attach);
})();
