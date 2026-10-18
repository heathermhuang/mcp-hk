export function recoveringResponse(release: string): Response {
  return Response.json({error: {code: 'SERVICE_RECOVERING', message: 'The backend is restoring its accepted snapshot. Retry shortly.'}}, {status: 503, headers: {'Retry-After': '10', 'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*', 'X-Mcp-Release': release, 'Strict-Transport-Security': 'max-age=31536000'}});
}

export async function normalizeBackendResponse(response: Response, release: string): Promise<Response> {
  const type=response.headers.get('content-type') || '';
  if ([500,502,503,504].includes(response.status) && !type.includes('application/json') && !type.includes('text/event-stream')) {
    await response.body?.cancel();
    return recoveringResponse(release);
  }
  const result=new Response(response.body,response);
  result.headers.set('X-Mcp-Release',release);result.headers.set('Strict-Transport-Security','max-age=31536000');return result;
}
