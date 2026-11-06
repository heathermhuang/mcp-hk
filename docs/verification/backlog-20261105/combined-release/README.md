# Checkpoint and published-request release — 6 November 2026

PRs #154 and #155 are deployed at
`fc71d10ee602cf539ee399fa47fef29441723056`. All five exact-main CI groups passed,
with 908 local Python tests (122 expected skips), quality/types and 173 Worker
tests. Worker version `f36c1d43-5c8e-4a4a-ba35-a484ff830e8d`, application and
running-instance version 78 adopted image
`sha256:a075e2c82ef0e4a70d57376ecabbcb211fb849a095b6e0a2ef8ffc07b4d8e906`.
Private controller diagnostics subsequently identified the same source commit.
Earlier old-controller observations are retained; no second deployment or forced
restart was used to resolve the normal deferred-adoption interval.

The checkpoint fallback is lossless on a fixed production restore: a fast
123.6 MB copy became 113.7 MB while all 36 tables remained byte-equivalent.
Maintenance checkpoints above 120 MB recompress the same isolated database and
capture set at level 6 before the unchanged transfer ceiling. Later live writes
belong to the next checkpoint. Local timings are not deployed CPU claims, and
manual authenticated backups already request level 6. A natural resource checkpoint at 05:35:09 UTC subsequently produced
113,893,239 bytes with gzip extra flags 0. The resource endpoint requests level 1,
so this independently observes the deployed balanced fallback without an operator
refresh or artificial data; see `native-backup-observation.json`.

The Lands Department's JSON catalogue resource points to an HTML API
specification. The exact published contract now requires caller-supplied `q` and
uses the fixed documented versioned endpoint. Actual hosted `cultural centre`
queries returned 27 source matches with HTTP/native MCP data parity and preserved
action context. Missing input returned no borrowed choices or default query.
Coordinates remain native/unreviewed; proximity stays held. These are returned
matches, not unique places, GeoAddress identities or a complete location inventory.

The earlier 135-root investigation produced 16 complete schemas and three
parameter-required interfaces. Fifteen default-root queries passed HTTP/native
MCP proof. One default response exceeded the unchanged response limit; explicit
structural inspection of its three native parent positions established
`common/0/vacancies`, returning 62 source rows with client parity. The other two
positions were absent, not provider denials. The full parent payload remains
limited. Parsing, schema-drift and capacity failures remain internal unfinished
work; this is not whole-dataset or semantic qualification.

The fresh post-client archive
`3f42adfad3a41de8cc99f905d5c5411477ac28308655c578c0064f473ff569f2`
restored 329,687,040 SQLite bytes / 360,842,323 total bytes from a
114,084,592-byte immutable R2 object. Integrity/capture hashes, registry, packs,
two inventory generations, six bindings, 84 workbook choices, three WFS scopes,
34 prior HKMA facts and 13 pre-checkpoint JSON variant facts passed. The new lookup,
old/new reads, options and scoped actions passed restored HTTP/native MCP checks
with zero provider requests. No provider denial was retried for this release.

A fresh native pre-pause schedule read returned 401. That failed observation is
retained and is not counted as verified. The existing-grant CLI operation and
subsequent native read succeeded, confirming the four preserved schedules. The
full propagation window was timed from that verified pause. All five original
schedules were independently verified restored, final health/readiness passed,
only the owned slot was released, and the exact two frozen-lane children resumed.
No new credential, service, schedule, quota, proxy or source-semantic approval was
introduced. The wider frozen programme remains open.
