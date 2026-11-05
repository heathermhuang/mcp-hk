# Backlog execution checkpoint

Frozen inventory date: 5 November 2026. Execution continues 6 November (Singapore).
Authority and finite work packages: [PLAN.md](PLAN.md). Primary checkout preserved;
implementation is isolated on `codex/backlog-end-to-end`, based on `b4aaae1`.

First unfinished work: open/qualify the integrated implementation PR, coordinated
release and source/client proof; then all unblocked selected reads and reader
corrections across the exact candidate ledger. The programme is not complete.

## Evidence states

- Source: all 271 frozen uncovered selection-resource metadata reads settled once.
  Four 403s are exact access holds. A recovering-runtime response remains pending,
  not an external source refusal. Options do not establish accepted record access.
- Source: four full official point exports and an issue-scoped Census series were
  captured and qualified. Nine KMB stop records support the narrowly documented
  bilingual pole-code annotation inference. A TD point 64 m away remains unverified.
- Local: original-source HTTP/native FastMCP replay passed for all four new point
  bindings and a 56-row Census series. Shared WFS protocol/scope, exact-count,
  variant/occurrence, failure, deadline and new-source regressions are implemented.
- Bus: a local candidate/actual resource-path NLB comparison settled 11 expanded
  candidates with seven resource lookups. Earlier KMB mismatch/deadline/recovering
  attempts are retained; new-code production KMB and NLB HTTP/MCP proof is pending.
- Recovery: full production-checkpoint clone accepted five original sources;
  the selected hybrid checkpoint restored 311,255,040 bytes from 106,745,164 archive
  bytes. All 36 logical table hashes/counts match. No facts or limits were removed.
  Ordinary VACUUM saved zero. All-compressed metadata's 145 MB archive was rejected.
- CI: pending current PR head. Deployment: prior released source `0444e8c` remains.
  Actual new-code public HTTP/MCP and fresh production backup/restore are pending.

## Artifact map

- `candidates.json.gz`: exact full-family and residual candidate ledger; read-only.
- `uncovered-selection-discovery.json.gz`: every initial uncovered resource outcome.
- `selector-pilot.json`: bounded initial discovery and accepted/failing pilot reads.
- `point-qualification.json`, `point-replay.json`: source facts and local client proof.
- `census-report-replay.json`: original issue/table/series, dictionaries and raw strings.
- `bus-source-contracts.json`, `kmb-name-qualification.json`: source rules/inferences.
- `pre-deploy-operator-rehearsal.json`: dated local candidate/actual resource-path proof.
- `pre-expansion-restore.json`: newer immutable accepted checkpoint and size baseline.
- `compaction-experiment.json`: zero-gain, lossless isolated VACUUM experiment.
- `growth-pilot.json`: five-source acceptance under the prior checkpoint encoding.
- `compact-growth-pilot.json`: rejected all-compressed encoding experiment.
- `hybrid-growth-pilot.json`, `hybrid-logical-proof.json`: chosen recovery encoding.

## Focused review and debug receipts

DEBUG REPORT — scope routing: a selected WFS GetFeature request returned REST
`LAYER_REQUIRED`. Root cause: host-path REST detection ran before WFS, including
published CSV feature URLs. Fix: shared access-protocol detection, exact inventoried
feature-type retention, matched-count JSON reads and rejection of unpreserved query
scope. Regression: ArcGIS-hosted WFS/CSV selected reads, namespace mismatch,
query-scope/imagery checks and noninteger/bool/unknown counts. Local status: fixed;
actual source acceptance remains a rollout gate.

DEBUG REPORT — KMB identity: all nine sampled names failed exact TD comparison.
Root cause: the current official records append the same pole code in both languages.
Fix: only that identical final `(AA999)` annotation is separated for comparison;
original names, 35 m distance and route/occurrence checks remain. Evidence: nine
source details, five exact-name/distance matches; changed names and a 64 m coordinate
disagreement remain held. Regression: bilingual mismatch and ordinary parentheses.
Local status: fixed; production source/client validation pending.

DEBUG REPORT — recovery capacity: expanded JSON consumed restored-database headroom.
Root cause: checkpoint formatting expanded every compressed schema row. Fix: retain
lossless schema compression in the isolated copy while inventory shares archive
compression. Evidence: 36 table hashes/counts and isolated restore. Regression:
legacy-text/native-compressed source metadata both retain exact IDs/cache and keep
live encoding unchanged. No pruning, quota or service change. Local status: fixed;
fresh production accepted checkpoint/restore remains required.

The initial point drift test reused a fresh cache; it now invokes the existing
source-review context to exercise a real changed-file read. A rehearsal harness's
internal/public argument mismatch and non-JSON response handling were corrected;
these were local verification defects, not production source clearances.

Release preflight source correction: CSDI rejected `application/json` and advertised
`GEOJSON`; its JSON omitted native counts. The follow-up repair negotiates the exact
advertised format, reconciles WFS 2 native hits before/after, invalidates old family
variants and preserves the existing row/byte limits. Actual original-source local
HTTP/native MCP returned 22 count-reconciled RVD028 features in four source requests.
No feature identity or atomic publication snapshot is inferred. Seven regressions
cover unsupported formats, changing/unknown/conflicting counts, truncation and the
unchanged row bound. Receipt: `wfs-source-qualification.json`. Deployment was held;
the earlier production release remained active with only resource cron paused.

The GitHub Actions startup incident deferred deployment. All five original crons
were independently read back, the old `0444e8c` backend remained healthy, and the
owned slot was released with no Worker/container rollout or lease clearing.
The incident has since recovered; required current-head CI still gates release.

Large-source follow-up: Slopes' native count is 61,527 but its 22,406,023-byte
GeoJSON response contains only the provider's first 10,000 features. The new WFS
path uses advertised Esri JSON, the native OID declaration and its explicit FID
alias, bounded native pages, strict observed ID order and before/after counts.
Projected EPSG:2326 geometry stays native. Local full-source collection stopped
on an actual HTTP 403; no partial scan was accepted. The full production scan is
pending, not qualified by partial evidence. `wfs-large-source-checkpoint.json`
retains this boundary. Raingauge has an independently observed 1,126,191 rows,
above the unchanged one-million ArcGIS ceiling; its exact internal capacity hold
is retained separately, without calling it a provider refusal.
