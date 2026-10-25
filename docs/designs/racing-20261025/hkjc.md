# HKJC racing: implementation and live acceptance plan

Date: 25 October 2026. Owner: the separate HKJC execution chat. Read
[shared.md](shared.md) first; it defines release serialization, budgets, recovery,
permissions, test requirements and the meaning of completion. This track owns
P8–P10 from the original roadmap. It has no live racing pack at the planning baseline.

## 1. Outcome, source evidence and scope

Deliver a read-only bilingual racing explorer with REST/MCP access to qualified
results and profiles, measured historical coverage, and a distinctly dated series
of prospective odds/pool/change observations where access permits. Use primary
HKJC facts and independently licensed materials only. No paid Renavon copying,
bet placement, predictions, account data, video/image redistribution or inferred
historical odds. Mark Six and football are separate products outside this racing
track, even when listed in the vendor catalogue.

Official pages checked on 25 October:

- [Local results](https://racing.hkjc.com/en-us/local/information/localresults):
  the old `Racing/LocalResults.aspx` route redirects here. Qualify route stability
  and date/race navigation; do not assume the old HTML parser will work.
- [HKJC disclaimer](https://www.hkjc.com/en-us/disclaimer): information is supplied
  without assurances of accuracy/timeliness/completeness; it does not establish our
  automated collection or republication rights.
- [Media-system copyright](https://mcs.hkjc.com/Copyright): restricts republication
  and redistribution without written consent on that service. It is a warning to
  qualify each actual service, not proof that one service's terms govern all others.

No specific automated route, historical-range entitlement, retained-cache right,
public API right or export permission has been established for this plan. First
search existing project-owned permission evidence. Then qualify exact results,
profiles, sectionals, dividends, trials, comments, rankings, changes and odds/pools
routes separately. No probe of hidden endpoints, session replay, anti-bot bypass or
purchase. Prepare an unsent intended-use request if needed; do not send it without
explicit human authorisation. Continue schema, synthetic parser contracts, offline
tests and disabled integration while source-dependent steps remain blocked.

Coverage is not a single boolean. Map each original source-map family to an actual
route, fields, date range, permissions, collector, tests and enabled mode. Deduplicate
`race_results` versus `race_results_core`; they may describe the same fact family.
Barrier trials, running comments, jockey/trainer rankings, track conditions and
jackpots need explicit qualified/implemented/unavailable dispositions. A results
pilot cannot be labelled parity with all vendor racing tables.

## 2. Source and data contracts

Create a source-specific schema and indexes through an additive migration:

| Relation | Stable key and essential fields |
|---|---|
| meetings | Official meeting ID if available; otherwise deterministic HKJC/date/venue key with derivation version; season, local date, course, source status |
| races | Source race ID plus meeting/race number; scheduled/actual time precision, class, distance metres, surface, course, going, status |
| participants | Namespaced official horse, jockey and trainer IDs; observed names/aliases separately; no name-only identity merge |
| runners | Race + official runner/horse identity; saddlecloth number separate from draw, weight/claim units, source declared/withdrawn status |
| results | Runner + result revision; raw placing/status, numeric placing where meaningful, dead-heat grouping, non-finisher/disqualified flags, margins, time and source units |
| profile_observations | Participant ID + capture; effective dates only when supplied, attributes as observed; current profile values never backfill an earlier race |
| sectionals | Race/runner/segment source key, segment distance/time/unit/precision and revision; race-level and individual sectionals stay distinct |
| dividends | Race or multi-race pool identity + combination + revision; ordered/unordered pool semantics, decimal HKD amount and published stake basis, refund/jackpot/carryover status |
| trials/comments/rankings | Separate qualified fact types, source IDs/period/metric/units and capture; avoid copying large copyrighted narratives by default |
| observations | Series/race/market/selection + source timestamp + observed UTC + sequence, odds/pool/change type, raw units, market state and capture |
| coverage | Expected meeting/race/range inventory, captured/validated/published counts, missing ranges, exceptional states, source cadence and reconciliation proof |

Keep source text alongside parsed numbers where permitted. Decimal monetary/odds
values use Decimal/NUMERIC, never binary floating arithmetic. A time like `1:09.23`
needs an explicit seconds conversion and precision; missing, withdrawn, abandoned,
dead heat and non-finisher are not zero. Stable keys must survive reordered rows
and amended results. A race number or annual race index alone is not globally unique.

Preserve amendments as append-only observations with a supersedes link and dated
current-selection rule. No destructive overwrite of an accepted result. Unknown
result codes block the affected group and generate a schema-drift receipt rather
than being guessed. Results-only pages may omit withdrawals; reconcile with a
qualified declared-runner source before claiming all runners. Publish completeness
dimensions separately when only result finishers are available.

## 3. Work packages and sequencing

| ID | Depends on | Implementation | Acceptance |
|---|---|---|---|
| R01 | Baseline | Inventory qualified routes/modes/terms, current repository contracts and mapped families; pin one completed meeting and one completed season from official inventory | Evidence matrix, exact range and no implied access grant |
| R02 | R01 contract; no live reads required | Migration, typed records, source policy, capture/run/coverage state, read-only grants and deterministic normalisation | Fresh/mixed migration order, ID/unit/revision tests and no source collision |
| R03 | R02 | Offline parsers and fixture corpus for both language/layout variants; bounded collector with checkpoint, holds, counters and idempotency | Synthetic drift/failure/resume tests pass; zero provider traffic with collection disabled |
| R04 | R01 access, R03 | One complete meeting: enumerate all races, declared/result runners, permitted profiles and all relevant pages | Every expected race and runner reconciled; anomalies/gaps explicit; no sample substituted for meeting coverage |
| R05 | R04 | Version-pinned backend/domain APIs, MCP, source status and bilingual UI; prebuilt permitted downloads | Shared-contract tests plus actual local rendered journeys; denied modes unavailable |
| R06 | R04–05 recovery | A complete finished season in bounded resumable batches; preserve any inaccessible/abandoned/postponed meeting evidence | Official meeting inventory, all races/runner sets and range ledger reconcile; pilot restore compares all facts |
| R07 | R06 measurements | Resumable approved history backfill; sectionals/dividends and remaining permitted profile/trial/comment/ranking/track/jackpot families | Earliest/latest available range and every gap documented per family; no unbounded full sweep |
| R08 | R04 + separate access/capacity gate | Prospective odds/pool/changes collector, series contract, observed start, cadence, retention, deterministic schedule and health | Measured timestamped series, stopped/suspended/closed states, missed-sample gaps, quota and recovery proofs |
| R09 | Candidate complete | Fresh code/data/security review, fixes, full checks, source-qualified real tests | No unresolved release-blocking findings; exact pushed HEAD CI/checks pass |
| R10 | R09 + shared release slot | Merge and deploy backend then gateway; qualify accepted versions; activate only allowed modes and schedules | Live matrix, actual downloads where allowed, fresh offsite restore, ordinary scheduled observation and rollback proof |

R04–R06 are P8; R07 is P9; R08 is P10. They can ship useful accepted increments,
but the final report must state which milestone/family is complete. Do not stop
after the first meeting when the authorised season/backfill work can proceed.
History's endpoint is the earliest range the qualified source actually makes
available, not an invented vendor count. Missing historical odds remain unavailable.

Initial collection ceilings are in shared.md. The season collector must checkpoint
when caps are exhausted and resume later. Establish a stable discovery inventory;
reconcile late corrections by bounded recent-range rereads, not a full-history scan
each day. Closed past races may still have amendments, so retention of an old
checksum does not establish permanent immutability.

P10 starts with one qualified meeting/market and a measured capture window. Write
a capacity calculation before scheduling: samples/day × markets × selections ×
bytes/row × retention, plus indexes/WAL/backups/restore peak. Set cadence to fit
permitted quotas and shared allocation; report the achieved cadence, not a promised
real-time feed. Keep raw/source timestamp versus observation delay distinct. This
plan authorises engineering within existing resources, not continuous high-frequency
collection at any cost. Where rights or capacity prevent a mode, deliver disabled
engineering and the concrete unresolved decision without claiming P10 live.

## 4. Public contracts and user journey

Proposed additive REST/MCP pairs; confirm names against current main before coding:

| REST | MCP | Behaviour |
|---|---|---|
| `GET /api/v1/racing/races` | `hk_racing_search` | Date/season/venue filters, optional permitted horse lookup, stable version/cursor |
| `GET /api/v1/racing/races/{race_id}/results` | `hk_racing_results` | Race metadata, complete declared coverage and paged result runners; revisions explicit |
| `GET /api/v1/racing/participants/{participant_id}` | `hk_racing_profile` | Typed horse/jockey/trainer identity and dated profile, bounded race history |
| `GET /api/v1/racing/observations` | `hk_racing_observations` | Separate prospective series, strict race/market/time window, limit/cursor and measured gaps |
| `GET /api/v1/racing/status` | `hk_racing_status` | Enabled families, accepted version/ranges, incomplete groups, last success and source hold |

Result detail may include bounded sectionals/dividends or links to dedicated paged
subresources; do not overflow the response ceiling. Status must distinguish source
unavailable, no races scheduled, complete empty result, incomplete range and stale
accepted data. API responses carry provenance/cutoff, series start and coverage.
No endpoint accepts arbitrary URLs or causes a provider scrape on an anonymous read.
Public reads use accepted stored versions; any on-demand verification variant needs
its own explicit qualification, budget and UX first.

Add `/racing` with date/venue selection -> meeting -> race -> participant, source
notice and explicit family/range coverage. Show withdrawals/status text, ties and
units consistently in English/繁中. A sample empty date cannot be presented as a
source outage. Prospective charts/tables label actual start and gaps; avoid invented
history or implied betting advice. Download selection is constrained to qualified
families/versions, with working CSV/JSON/manifest/notice where exports are allowed.

## 5. Verification matrix

| Layer | Required cases and pass condition |
|---|---|
| Parsing/identity | Two venues, both languages, reordered columns/rows, Unicode names, source-ID reuse across seasons, leading-zero IDs; changed unknown layout blocks group |
| Race semantics | Withdrawal/late scratching, cancellation/abandonment/postponement, dead heat, non-finisher, disqualification, amendments, horse number != draw, missing margin/time, weight claims and units |
| Dividends/sectionals | Ordered versus unordered combinations, multi-race pools, F/M notation only per documented dictionary, refunds/carryovers, Decimal exactness, absent/incomplete segments and units |
| Collector | Duplicated run, session/setup reads included, 304/429/503/403, content-type/oversize/timeout, cap mid-meeting, process crash/resume, no empty publish, no raw/private output leak |
| Real source pilot | Reconcile every listed race and runner for complete meeting then every meeting/race in season; use source inventory distinct from imported counts; independently recalculate keys/counts |
| PostgreSQL | Mixed migration order, reader grants, indexed plans/latency at measured size, cursor across new publication, compare-and-swap conflict, rollback and source-isolated writes |
| Prospective series | Duplicate timestamps, out-of-order arrival, corrected/suspended/closed markets, clock skew, gaps, elapsed/delay calculations, budget/day rollover and retention/cursor compatibility |
| Recovery | Full pilot relation and hash equality after independent offsite download/restore; code rollback keeps compatible pointer; source A restore cannot replace CR/Enigma |
| Live product | Same pinned values/coverage in REST/MCP/browser EN/繁中, actual archive download/contents, mobile/keyboard/empty/stale/gated states; existing packs regressions pass |

Use independently constructed expected records and source meeting/season inventory,
not assertions derived only from the parser under test. Synthetic exotic cases
test code without implying those cases occurred in the real pilot. Networked tests
run only against approved routes and consume the persisted provider budget.

## 6. Release and done evidence

Follow the shared slot, least-privilege backend-first deployment, source-mode flags,
actual DO adoption, schedule restoration and fresh recovery proof. Roll back by
disabling only affected racing modes/schedules and atomically selecting the previous
compatible racing version; retain observations/receipts and unrelated sources. A
schema rollback is not destructive migration reversal. Rehearse reader/code fallback
against the previous compatible schema before release.

Commit `docs/verification/racing-<date>/` with source matrix, field dictionary,
meeting/season reconciliation, per-family historical gaps, series cadence/retention
measurements, review fixes, exact tests/CI, PRs/commits, live artifacts and rollback/
restore/scheduled-run receipts. Keep licensed captures private as required. Completion
requires every authorised reachable family/milestone above accounted for and live
where qualified. If an external right or paid route is necessary, report precisely
what is implemented/tested, the exact activation step held, and the prepared decision;
do not call the whole racing track finished from scaffold deployment.
