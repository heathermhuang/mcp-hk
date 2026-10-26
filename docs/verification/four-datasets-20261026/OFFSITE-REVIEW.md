# Enlarged company backup transport

26 October 2026. The PR 92 source restore attempt failed at offsite upload and
retained the prior recovery state. Its local dump is 139,108,317 bytes and the
before/after source fingerprints are identical. The existing zone API reports
`Free Website`; Cloudflare documents a 100 MB request-body ceiling for that plan.
The single-request upload cannot carry this enlarged state. A headers-only probe
sent no dump bytes and received no early response, so it is not claimed as an
observed HTTP 413. The failed job and its artifacts remain retained.

The repair uses up to four 64 MiB requests without changing source/host/storage
quotas, infrastructure or credentials. Each immutable part receives provider SHA-256
verification and an independent HTTP retrieval. The complete local reassembly is
hashed again. Before accepting the manifest, the gateway checks consecutive bounded
part names, sizes, hashes, total and its own streamed aggregate SHA-256. Verification
bytes count against the existing daily read allowance. Mixed legacy/part objects,
missing parts, reordered parts and incorrect aggregate hashes cannot publish.

The old complete-dump HEAD/GET contract remains available through the validated
manifest, including for retention checks. Legacy single-object backups still work.
Only the existing source prefix is accessible; arbitrary names, other prefixes,
delete/list and broader credentials remain denied. A failed part retains partial
evidence and never creates a recovery manifest. Safe fixed HTTP status codes improve
failure receipts without exposing source tokens, bodies or private URLs.

Regression demonstration against unchanged main: the two new Python transport
tests fail and the two new Worker protocol tests fail. With the repair, all four
Python uploader tests and all nine source-specific Worker tests pass, including
legacy contracts. Worker type checking passes. Full exact-head checks and CI are
separate release gates.

Focused correctness/security/recovery review: no blocking findings. The actual
139 MB production roundtrip, source physical restore/performance, runtime adoption
and restored schedules must still pass before claiming restored growth eligibility.
