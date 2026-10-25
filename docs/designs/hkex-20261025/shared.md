# Shared implementation, publication and release requirements

Date: 25 October 2026. Applies to HKJC, SFC and HKEX execution chats. Read together
with the source-specific plan and current mcp-hk AGENTS.md/runbooks. Where production
has advanced, inspect actual state and preserve the stricter verified constraint.

## 1. Independent source ownership and shared files

Use separate isolated clones, `codex/` branches, local test databases, fixture
directories and evidence folders. Suggested source modules are
`curated/racing/`, `curated/sfc/`, `curated/hkex/`, with domain adapters
`racing.py`, `sfc.py`, `hkex.py` and corresponding tool registration modules.
Names are proposals; follow established code conventions. Avoid copying the CR
collector wholesale or building a new framework for these three sources.

Reserve additive migration names `002_racing.sql`, `003_sfc.sql`, and
`004_hkex.sql` only after checking current main. These numbers are identifiers,
not an assumption about landing order. Each migration must work on baseline and
with any subset/order of sibling source migrations; otherwise declare a genuine
dependency and land it first. Never edit an already applied migration. Shared
changes should be minimal and backwards compatible. Rebase onto current main,
reconcile registration/discovery/configuration changes and run affected checks
before each merge. Do not restore an old full configuration over a sibling release.

Each pack has independent configuration for collection, retention, publication,
history, API/MCP, exports and scheduling. Default new modes off. A policy record
must bind source, service route, purpose, allowed fields/modes, retention period,
cadence, evidence reference/hash, qualification date and recheck/expiry rule.
Unknown, denied and allowed are separate states; unknown never enables a mode.
Revocation/expiry disables affected modes and serves an honest status without
silently deleting accepted evidence or altering another source.
Configuration flags alone cannot override this policy. Activation is an audited
operator/deployment action against a checksum-pinned reviewed policy record, never
a public request parameter. Recheck qualification when routes/fields/purpose or
terms materially change. Test expiry/revocation during a running collection and
before publication/export, so an earlier admission cannot bypass a later hold.

## 2. Common capture and version contract

Reuse existing curated publication/backup primitives where suitable; generalise
only the parts needed by an actual source. Every accepted fact references a capture
and deterministic transform identity. Store source ID/namespace, canonical approved
location, retrieval UTC, source timezone/date precision, raw checksum, transform
code hash, run ID, terms/policy reference and validation result. Store source bytes
only if retention is permitted; do not publish them merely because private retention
is allowed. Receipts and public errors contain no secrets, signed object URLs,
session material or user search terms.

Separate event/effective date, filing/submission date, source publication date,
source-declared coverage, observation time and our release publication time. Null
and unknown precision stay explicit. Rechecking a file does not advance the facts'
cutoff. Source time without a timezone remains qualified as such, not invented UTC.
Identifiers remain strings, preserving leading zeros. Never merge entities across
Webb, BRN, CE, issuer or racing namespaces by name.

Stages are `discovered -> captured -> parsed -> validated -> restore-qualified ->
published`, with failed/partial/interrupted states and independently recorded job,
backup and publication outcomes. Publication uses a source-specific atomic accepted
pointer plus expected-old-version comparison. A failed run preserves the last
accepted pointer. Partial groups do not masquerade as complete meetings, corporate
records or filing windows. Bad optional groups can remain explicit gaps only when
the declared release coverage excludes them.

Jobs are deterministic CLI/systemd work, not recurring model calls. Start with a
bounded inventory/checkpoint comparison; unchanged state exits without full audits,
backups or refetches. Persist idempotency keys `(source, operation, scheduledFor)`;
count failed and uncertain requests and retain crash reservations. One source
session at a time, approved fixed origins, bounded redirects/body/timeout, persisted
Retry-After/403 hold, no alternate proxies/endpoints to evade source controls.
An interrupted request is unknown until reconciled, not success or a free retry.

Initial engineering ceilings, effective only after route qualification:

| Source | Reads/run | Reads/UTC day | Bytes/run | Bytes/day | Work unit |
|---|---:|---:|---:|---:|---|
| Racing | 40 | 200 | 16 MiB | 64 MiB | One complete meeting pilot; then resumable small batches |
| SFC | 25 | 100 | 8 MiB | 16 MiB | Up to 25 exact corporate CE references |
| HKEX | 40 | 100 | 16 MiB | 32 MiB | One issuer, seven calendar days, resumable pagination |

These are conservative proposed caps, not provider-approved allowances. Lower
provider limits prevail, all listing/detail/session/retry reads count, and a cap
hit yields an incomplete checkpoint. Do not truncate and publish as complete. Bound
each run to ten minutes; stop and resume rather than keep a release lease occupied.
SFC's 25-read cap may require fewer than 25 entities if discovery/detail takes more
than one read. Caps may be revised with measured cost/capacity and documented review
within existing authority; new spend/access rights still need a concrete decision.

## 3. Serving and product contracts

Persistent PostgreSQL remains outside the gateway SQLite/R2 snapshot. The private
backend uses the existing fixed authenticated HTTPS origin and SELECT-only serving
role. New writers receive only source-scoped owner privileges. No caller-supplied
SQL, URL, host, schema or filesystem path. Scope grants and schema isolation so
source A cannot publish source B or mutate Enigma/CR observations.

Public REST, MCP and browser use one domain adapter and the same version, policy,
errors, field definitions and coverage. Register static status/notice paths before
dynamic IDs. Preserve existing company API/tool contracts and historical warnings.
Optional source failure does not fail base `/readyz` or remove unrelated packs.
Do not advertise a disabled data tool/endpoint as available. If a defined endpoint
remains registered for compatibility, return the documented source-specific
unavailable envelope without invented empty success. Keep operational/private routes
out of public OpenAPI and MCP. Status may explain a source gate without exposing
restricted data or confidential correspondence.

Read defaults: limit 20, maximum 100; literal NFKC/casefold prefix search with query
2–200 characters where search is allowed. Exact IDs do not use fuzzy/name merging.
Stable total ordering with signed cursors binds source, version, filters, order and
expiry; preserve the existing 48-hour cursor retention only where source retention
allows it. If a source cannot retain that window, define a shorter explicit expiry
and a typed expired-version result before activation. Never hold a transaction
between requests. Preserve backend 2 s SQL/250 ms lock timeout, four shared query
slots and 2 MiB output ceiling. Existing public 60/min/IP, 50,000/day total and
10,000/day address budgets are aggregate, not fresh allowances per pack. Preserve
64 KiB request-body limit. Schedulers/source collectors need their own durable
provider budgets; public query limits do not grant collection authority.

Keep the current bilingual EN/繁中 forest-green UI and plain JS/CSS conventions.
New pages need source/date/coverage/rights labels, working examples, empty/error/
stale/gated states, source-qualified links, accessible keyboard controls, and
bounded mobile tables. Test 320/390/768/1280 px. Reuse current source/status/source
notice components; no framework, account, payment or design-system migration.
Discovery, generated JSON, OpenAPI, MCP schemas, API docs and examples must describe
only the modes actually enabled. Test generated assets for drift.

Exports, if allowed, are immutable prebuilt versioned artifacts with schema,
manifest, field definitions, source attribution, cutoff and checksums. Preserve
string IDs in JSON and CSV; mitigate CSV formula injection without corrupting raw
facts. Bound uncompressed/total archive size and safe paths. Never run a full SQL
export in a request. Actual browser download and archive content verification are
required, not just a HEAD/content-type check. A denied export mode has no misleading
download button or runtime bypass.

## 4. Host capacity and recovery

Use existing curated.mcp.hk infrastructure within the recorded US$30/month approval
(US$28.80 before tax at the recorded baseline); recheck actual cost and capacity.
No three independent budgets against the same disk. Record one combined capacity
sheet covering accepted/staging versions, all three sources, Enigma/CR, raw captures,
indexes, WAL, local dumps, offsite objects and a fresh restore database. Propose a
20 GiB minimum free-space reserve for **new** dataset growth, without weakening
the existing collector's guard. Measure actual host free bytes, RSS/CPU, database
size and restore peak first. Initially reserve at most 1 GiB additional durable
growth per track; exceeding it requires a revised measured allocation and review,
not unbounded collection. Reserve capacity atomically in the release ledger below.

Before publication, create a complete source/version backup including metadata,
lineage, captures where permitted, pointers, policy and required dependencies;
upload to the existing private offsite store, download, checksum and restore into
a new isolated DB. Use least-privilege readers there and compare all pilot facts,
counts, relations and manifest hashes, not only a sample. Retain last accepted
proof and code/schema compatibility. Enigma and CR recovery remain intact.
Gateway snapshot restore alone cannot prove these PostgreSQL sources recover.

No new data-growth scheduler until the host's current recovery gate permits it.
A release-time manual restore proves that release only. Claim daily RPO only after
an actual ordinary scheduled collection/backup/offsite-copy/restore sequence meets
the declared window. Existing company-maintenance RPO remains separately owned.
Include each new source in compatible deterministic daily backup/offsite scheduling
and verify an ordinary occurrence; fail closed on backup errors and growth limits.
Do not add three overlapping full-DB backup timers when one qualified job can cover
them; coordinate ownership and backup/schema coverage explicitly.

## 5. Release serialization across the three chats

Before merging shared integration changes or mutating production, claim a common
local release slot at the absolute path
`/Users/heatherm/Documents/ChatGPT/hk-app/research/mcp-hk-dataset-onboarding-20261025/release.lock`.
Create its parent if needed, then acquire by **atomic directory creation**. A
pre-existing directory means busy; do not run production mutations. Write an
owner receipt inside containing source/chat ID, random owner token, checkout,
commit, operation, start/update UTC and rollback reference; keep secrets out.
Maintain a sibling append-only `releases.jsonl` with claimed/preflight/migrated/
deployed/verified/restored-schedules/released or failed/unknown states. Reserve
source disk allocations in the same serialized ledger. Confirm receipt token before
each phase and before releasing your own claim; only the owner removes its receipt
and empty lock directory after all production state is known and schedules restored.
Never expire, steal or clear another/unknown claim because a timestamp looks old.
Investigate the owner's process/receipts and obtain a concrete handover if needed.

The local slot coordinates these three chats; it **does not replace** PostgreSQL
advisory writer locks, Cloudflare maintenance/seed leases, expected-version checks,
or the existing company-maintenance owner. Before migration/rollout, inspect actual
active host jobs/timers, leases and current main. If company maintenance is active,
wait for the bounded job to settle. For schema changes that need quiet writes,
suspend only relevant timers at an acknowledged safe boundary, record every prior
timer state, drain the actual writer lock and restore exactly those states. A new
release claim alone is not permission to disable unrelated jobs. Published datasets
may advance while engineering proceeds; don't overwrite their accepted pointers.

Land source-scoped PRs independently when their checks pass; the release slot is
held for the short merge/integration/deploy window, never the entire implementation
or a provider-permission wait. Re-read newest remote main after acquiring it, resolve
conflicts, verify the exact candidate, and avoid overwriting another release.
An unchanged queued task backs off; no repeated full audits or model monitoring.

Deploy backend/schema with backwards-compatible readers before enabling a consumer.
Use immutable `/opt/mcp-hk-releases/<commit>` directories, preserve dirty `/opt/mcp-hk`,
and change only the intended compose service/release pointer; do not replace
PostgreSQL, proxy or the separate official maintenance runner with a stale checkout.
For Worker/DO changes follow docs/production.md: temporarily remove only the resource
cron, preserve the other four, allow up to 15 min propagation, drain actual leases,
roll out, and verify the actual controller contract/release, backend capabilities,
container policy/image and accepted-pack readiness. Static release headers are
insufficient. An immediate DO update, if required, is only inside the documented
paused window; preserve normal checked-in defaults. Restore all five schedules,
verify them, take a fresh accepted backup and run the required isolated restore.
Never clear a lease to make a deployment proceed. Failed/unknown phases retain
receipts and recovery artifacts; report the exact state and resolve before handover.

## 6. Review, tests and completion evidence

Each source implementation requires a fresh correctness/security/data-semantics
review after code is complete; fix actionable findings and repeat affected tests.
Review against this plan, not an invented minimum finding count. Check parser drift,
source rights, privacy, budgets, egress, backup coverage, SQL grants, cursor expiry,
concurrent publication, scope collisions, and disabled-mode exposure.

Run mandatory `bash scripts/check.sh all` in the implementation repository against
the exact pushed HEAD, install/preserve the required pre-push hook, and satisfy
Python 3.10/3.11/3.12 CI plus Worker types/tests/generated discovery checks as required
by current AGENTS.md. Real PostgreSQL integration tests must run; skipped DB tests
are not proof. Isolated fixtures must be labelled synthetic and avoid unlicensed
provider payloads. Network tests are separately gated, bounded and recorded.

Source-specific matrices below are in addition to full existing API/MCP/company/
restaurant/population/address/property/plate/discovery/auth regressions. On live
deployment verify actual REST and MCP values/version/coverage agree, EN/繁中 browser
journeys and permitted actual downloads work, disabled modes remain absent, and a
source failure preserves last accepted data. Check backend adoption and recovery,
then observe a normal scheduled source occurrence without substituting an operator
run. If the next ordinary occurrence is later, install a deterministic bounded
verification job/checkpoint under existing authority; record pending evidence and
do not claim it passed or create a recurring model audit.

Durable evidence: qualification matrix, schema/field contracts, source-range ledger,
pilot reconciliation, request/byte/cost receipts, review dispositions, exact test
commands/results and skipped reasons, PR/merge SHA, backend/Worker/DO adoption,
restore hashes, schedules before/after, real HTTP/MCP/browser/download artifacts,
rollback rehearsal and source-specific status. Keep private payloads/credentials
outside Git. Public report clearly separates implemented, tested, source-qualified,
deployed, live-observed and remaining blocked modes. Attach every created PR to its
own chat. Never mark the full source track complete merely because gated scaffolding
was deployed; finish all authorised unblocked work and identify the smallest exact
external decision for any remainder.
