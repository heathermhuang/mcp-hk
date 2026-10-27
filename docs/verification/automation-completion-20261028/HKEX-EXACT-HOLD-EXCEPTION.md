# Exact legacy-response inspection decision

Prepared 28 October 2026. No source action has been dispatched by this work.

Approve one quota-accounted GET of
`https://di.hkex.com.hk/di/NSForm3A.aspx?fn=DA20030606000076`
solely to inspect its response and sanitized redirect metadata. The original ledger
142 response was HTTP302 / 159 bytes. Current readback still has
SOURCE_ACCESS_HOLD with no deadline and zero unknown requests.

The implemented `curated.hkex_daily.inspection` uses the existing writer session
and request ledger; failed/unknown reads remain charged. It requires the exact
original response hash, the unchanged hold, existing 100/day and 32 MiB/day shared
ceilings and the minimum source interval. It reserves at most 400 KiB for one
20-second response, follows no redirect, performs no retry, retains no HTML, and
never clears or extends the hold. The exact approval evidence hash is a durable
single-use key. Unknown URL paths/query values, session material, credentials and
alternate authorities are withheld; only hashes and sanitized route shape survive.
No timer/CLI invokes this exceptional admission. Ordinary admission remains held.

An interrupted dispatch is unknown and requires reconciliation; it is never
silently repeated. Success does not activate legacy collection or qualify issuer,
filing inventory, forms/channels or revision closure. The 145-target audit remains
unchanged. No ESS credential, provider outreach, proxy or new endpoint is requested.

Verification: three real PostgreSQL tests passed with fabricated HTTP responses:
one-use charging/hold preservation, missing/incorrect approval and interrupted
reservation preservation, and exhaustion of the shared allowance. Eight offline
redirect tests cover credential/session redaction and exact route retention.

Decision needed: approve this exact one-response hold exception, or retain the hold
and leave the diagnostic undispatched. New transport/redirect qualification would
be a later separately evidenced decision.
