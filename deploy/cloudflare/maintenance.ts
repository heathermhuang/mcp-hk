export const EXPECTED_REVIEW_POLICY = 'source-review-4';
export function maintenanceRuntimeReady(value: unknown): boolean {
  return value !== null && typeof value === 'object' && 'sourceReviewPolicy' in value && value.sourceReviewPolicy === EXPECTED_REVIEW_POLICY;
}

type Controller = {
  maintain(pack: string): Promise<unknown>;
  operationDiagnostics(): Promise<{leaseUntil: number | null}>;
};

/** Report a held safety lease without clearing it or disguising it as an outage. */
export async function maintenanceResponse(app: Controller, pack: string, redact: (error: unknown) => string, now = Date.now()) {
  try { return Response.json(await app.maintain(pack)); }
  catch (error) {
    const message = redact(error);
    if (message.includes('DATA_RUNTIME_NOT_READY')) return Response.json({error:{code:'SERVICE_RECOVERING',message:'The data runtime is not ready for this maintenance version.'}},{status:503,headers:{'Retry-After':'30','Cache-Control':'no-store'}});
    if (message.includes('Maintenance already running')) {
      let retryAfter = 60;
      try {
        const state = await app.operationDiagnostics();
        retryAfter = Math.max(1, Math.min(900, Math.ceil(((state.leaseUntil || now + 60000) - now) / 1000)));
      } catch { /* A missing diagnostic never authorizes clearing the lease. */ }
      return Response.json({error: {code: 'MAINTENANCE_BUSY', message: 'A maintenance safety lease is held; retry after it expires.', retryAfterSeconds: retryAfter}}, {status: 409, headers: {'Retry-After': String(retryAfter), 'Cache-Control': 'no-store'}});
    }
    return Response.json({error: {code: 'MAINTENANCE_FAILED', message}}, {status: 503, headers: {'Cache-Control': 'no-store'}});
  }
}
