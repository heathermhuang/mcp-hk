/* Retry only our bounded cold-recovery signal, never provider/data failures. */
export async function fetchPublicJson(path, body) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const response = await fetch(path, {method: body ? 'POST' : 'GET', headers: body ? {'Content-Type': 'application/json'} : {}, body: body ? JSON.stringify(body) : undefined});
    let payload;
    try { payload = JSON.parse(await response.text()); }
    catch { throw new Error(`HTTP ${response.status}: The service did not return JSON data. Retry shortly.`); }
    if (response.status === 503 && payload.error?.code === 'SERVICE_RECOVERING' && attempt < 2) {
      const seconds = Math.min(30, Math.max(1, Number(response.headers.get('retry-after')) || 10));
      await new Promise(resolve => setTimeout(resolve, seconds * 1000));
      continue;
    }
    if (!response.ok) throw new Error(`${payload.error?.code || response.status}: ${payload.error?.message || 'Source unavailable'}`);
    return payload;
  }
}
