/* Retry only our bounded cold-recovery signal, never provider/data failures. */
export async function fetchPublicJson(path, body, {signal,attempts=3,capture} = {}) {
  for (let attempt = 0; attempt < attempts; attempt++) {
    const response = await fetch(path, {signal, method: body ? 'POST' : 'GET', headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    let payload;
    try { const raw = await response.text(); payload = JSON.parse(raw); if(response.ok) capture?.(raw); }
    catch { throw new Error(`HTTP ${response.status}: The service did not return JSON data. Retry shortly.`); }
    if (response.status === 503 && payload.error?.code === 'SERVICE_RECOVERING' && attempt < attempts-1 && (Number(response.headers.get('retry-after'))||10)<=30) {
      const seconds = Math.min(30, Math.max(1, Number(response.headers.get('retry-after')) || 10));
      await new Promise((resolve,reject) => {const timer=setTimeout(resolve,seconds*1000);signal?.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));},{once:true});});
      continue;
    }
    if (!response.ok) { const error=new Error(`${payload.error?.code || response.status}: ${payload.error?.message || 'Source unavailable'}`); error.code=payload.error?.code; error.retryAfter=Math.max(0,Number(response.headers.get('retry-after'))||0); throw error; }
    return payload;
  }
}
