# Exact held-redirect diagnostic

Historical ingestion is stopped on the recorded 15 July 2026 Happy Valley results
request, local attempt 298, outcome `DEVELOPMENT_HTTP_302`. Its target/headers were
not retained by the earlier collector. A 302 can represent ordinary navigation,
but its actual target must be inspected before extending a route or reclassifying
the source outcome. The existing HTTP403/429 and unknown-request controls remain.

This increment adds authenticated operator action `inspect_redirect`, accepting
only an existing numeric local attempt ID. The container requires that exact
attempt to remain held with `DEVELOPMENT_HTTP_302` and to have its corresponding
durable admission identity. Its recorded URL must pass the existing fixed results
route validator. Callers supply no URL, origin, query or credential.

The Durable Object admits at most one basic diagnostic per original held admission,
before provider dispatch, within the unchanged 200 reads / 64 MiB per UTC day and
400 KiB body reservation. Other pending/held requests, provider-denial records,
unknowns and exhausted budgets refuse this special admission. It never changes
the original hold or its conservative byte charge. Normal collection stays blocked.

The one GET uses the original URL and declared collector identity, without redirects
or forwarded operator credentials. It records status, bounded logical body hash/
bytes, truncation, time and a sanitized Location. Unknown query values, credentials,
session paths and unqualified origins are hashed without being copied. It retains
no raw HTML. A new provider denial is held; uncertain admission/transport/settlement
is recorded without another dispatch or automatic retry.

Inspection metadata has its own additive SQLite table and is included in future
all-table recovery fingerprints. A real checkpoint remains the operation response
body, with separate bounded inspection metadata; JSON cannot replace the R2
snapshot. The controller validates that metadata before saving the checkpoint.
The private response reports the saved backup and diagnostic, without publishing
a race, following the target or clearing any control.

The first production diagnostic completed with HTTP302 and an unqualified Location
hash, which did not retain enough routing information. `inspect_redirect_shape`
therefore permits one separately recorded instrumented read only after the first
completed, settled HTTP302 has that opaque target. It requires the same original
held request and unchanged aggregate source quotas. Unknowns, denials and other
outstanding controls refuse it. Its record captures HTTP/HTTPS scheme, same-provider
host, recognized static path words and query-key names. Opaque path parts,
credentials, unknown parameter values and session material stay redacted. The
original hold stays active, and neither operation can repeat after admission.

Tests cover exact selection, no credential forwarding/following, replay rejection,
provider/unknown/other-pending refusal, day quota, unchanged original hold, new
denial, timeout preservation, Location redaction and a real tar.gz checkpoint
response. A live diagnostic remains pending checked deployment. Its result will
determine the next narrowly qualified route/availability repair; it does not itself
qualify historical completeness or resume source collection.
