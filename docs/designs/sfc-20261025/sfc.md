# SFC corporate verification: implementation and live acceptance plan

Date: 25 October 2026. Owner: the separate SFC execution chat. Read
[shared.md](shared.md) first. This owns fresh corporate licence verification
(P7-01/02 and its own P7-05 acceptance), not historical Webb licence reconstruction,
the CR backlog, personal contact directories, or all SFC regulatory datasets.

## 1. Outcome and qualification boundary

Deliver exact CE-based corporate verification with official dated observations,
regulated-activity/status particulars, honest coverage and permitted REST/MCP/browser
surfaces. Keep historical Webb licence/staff relationships visibly historical and
source-separated. Do not relabel an archive record as a current SFC verification.

Official sources checked on 25 October:

- [Register entry point](https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Register-of-licensed-persons-and-registered-institutions)
  exposes name/CE, licence-type and corporate-business-activity searches.
- [Important legal information](https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Register-of-licensed-persons-and-registered-institutions/Public-register-of-licensed-persons-and-registered-institutions)
  limits use to the stated licence/registration-verification purposes, describes
  end-of-day updates and excludes former executive-officer records. It does not
  establish unrestricted automated bulk collection, history or redistribution.

Existing `docs/data/qualification/company-permission-briefs.md` is an **unsent**
request; `qualified_fixtures.py` validates synthetic CE records only. First inspect
existing project-owned correspondence/permissions, exact register routes and current
terms. Qualify intended-dealing verification, automation/session flow, cache TTL,
retained observations/history, backups, allowed corporate fields, public REST/MCP,
browser display, page downloads and aggregate exports independently. A UI checkbox
or our own purpose string cannot create source permission.

If only user-initiated verification is allowed, implement that qualified mode with
its exact cache/retention limits; do not install an ongoing bulk collector or public
directory. If even that route is unresolved, keep network collection and affected
public results disabled, prepare the precise request and complete independent
engineering. Provider outreach, new terms/fees or credential expansion require a
concrete human decision; this plan does not send the existing brief.

## 2. Scope and data model

The first approved cohort is **at most 25 exact corporate CE references**, chosen
deterministically from an already authorised corporate list or explicitly tracked
verification set. Establish that the tracked purpose itself is permitted; do not
mine a full register just to select 25 examples. Prefer sufficient variation in
corporate licence types/activities/statuses where qualified examples exist. Never
change a source identity or manufacturing a real suspended/revoked example to fill
test coverage; synthetic cases cover absent real examples.

SFO corporate verification is the initial scope. Registered institutions, AMLO/VA
regimes or temporary licences require explicit regime/type handling and may be
included only if qualified. If deferred, expose the exclusion. Reject individual
CE records from a corporate-only collector; CE syntax alone does not prove type.
Exclude marketing/complaint contacts, email/telephone, individual representative/RO
directories, inferred BRNs, former EO histories and disciplinary text expansion.
Do not infer safety, endorsement, performance or creditworthiness from licence status.

| Relation | Key and contract |
|---|---|
| corporate subjects | `sfc:ce:<CE>`; CE string validated against qualified grammar, source-declared entity type, names/language and exact licence regime/type |
| captures | Qualified route + source record key + raw/transform hash and observation time, source-declared cutoff/precision, policy reference; retained payload only if allowed |
| licence observations | Subject/capture; source status/code/raw label, registration/licence type, conditions allowed by policy, source effective dates versus observed date |
| activity observations | Subject/regime/activity/capture, start/end raw dates + precision, restrictions/conditions and source reference |
| changes | Previous/current observation, deterministic field-level difference, change observed interval; source effective date only when supplied |
| jobs/cohort/coverage | Exact requested CE set, successful/unknown/missing/rejected/stale results, run budgets, last success/attempt/hold and accepted version |

Null end date does not assert the licence is presently active. A missing search
result, timeout, denial or parser failure is unknown/failed, not a revocation.
Publication preserves last accepted observation and displays its age. Close a known
licence/activity interval only with source evidence; an observed absence may be a
separate fact and must not manufacture its effective end date. Observed changes
are not a complete regulatory event history. Source-declared status and our freshness
classification are separate fields.

Keep corporate CE identity distinct from archive organisation IDs and BRNs. Any
crosswalk must come from explicit qualified identifiers and cite evidence; otherwise
show separate search results/source panels. Name equality is never a join criterion.
Retention-limited captures and source-rights revocation need a tested policy that
does not promise unavailable history or violate cursor retention.

## 3. Work packages and dependencies

| ID | Depends on | Work | Acceptance |
|---|---|---|---|
| S01 | Current baseline | Verify precise purpose/mode evidence, source routes/fields/update limits and tracked cohort; refresh unsent request only where needed | Per-mode allowed/unresolved/denied record, exact source documents and no assumed automated/public rights |
| S02 | S01 contract | Add source-scoped schema, policy state, typed CE/regime/activity/status models, deterministic captures and migration | Fresh/mixed-order PostgreSQL migration, exact identity/type/temporal tests |
| S03 | S02 | Offline parsers/fixtures and bounded collector or qualified verification adapter; 25-read/run/100-day upper caps, concurrency one, persisted holds/checkpoints | Failure/no-result/type mismatch and disabled-network tests pass; all request classes count |
| S04 | S01 access, S03 | Up to 25 corporate CE pilot; manually reconcile every accepted field and reject ambiguous/entity-mismatched records | Full cohort receipt with actual source cutoff and independent comparisons; caps may yield smaller batches |
| S05 | S02–04 | Versioned private backend reader, shared public adapter, REST/MCP and source-specific status with independent mode switches | One response contract across surfaces; no historical archive promotion or purpose/mode bypass |
| S06 | S05 | Bilingual corporate verification journey, source/date/coverage explanations, allowed per-page downloads/history | Real rendered EN/繁中/mobile and accessibility journeys; prohibited contact/history/export fields absent |
| S07 | S04–06 | Correctness/security/data-semantics review, fixes, real PostgreSQL/failure/recovery tests and mandatory exact-HEAD checks/CI | No unresolved blocking finding; full pilot restore/equality and cursor/privacy proofs |
| S08 | S07 + shared slot + required mode rights | Merge, backend/schema then gateway rollout, qualify/publish pilot, activate only permitted output/update modes | Live REST/MCP/browser/download parity, actual adoption and schedules restored; previous packs healthy |
| S09 | S08 + permitted schedule | One ordinary scheduled check or genuine permitted verification request, backup/offsite restore and stable health | Actual occurrence evidence, bounded costs/holds, current source observation; no manual substitute for unattended proof |

S02/S03/disabled S05/S06 can proceed while a provider decision is pending. Do not
make new public directory data or retained history live in order to demonstrate
engineering progress. The corporate cohort must remain explicitly partial; 25
records never establish register-wide completeness.

For permitted periodic collection, propose one daily job after the source's
end-of-day update, initially 21:30 Asia/Hong_Kong (13:30 UTC). Validate the timing
against the qualified service and host jobs before enabling it. If the source only
states end of day without a firm clock, call the run a check at that time, not proof
that today's complete update has occurred. Prefer source-exposed cutoff markers;
otherwise expose their absence. No weekend/holiday semantics are invented. Duplicate
occurrences cannot double-run; bounded catch-up does not erase source holds.

## 4. REST, MCP and product contracts

Use a separate fresh-official namespace, preserving `/companies` archival behaviour:

| REST | MCP | Contract |
|---|---|---|
| `GET /api/v1/sfc/corporations/{ce}` | `hk_sfc_verify` | Exact corporate CE, permitted verification purpose and source/version; status/activities/conditions/cutoff/observed age |
| `GET /api/v1/sfc/corporations` | `hk_sfc_search` | Only if directory/search redistribution is allowed; exact CE or bounded literal corporate prefix, partial cohort coverage |
| `GET /api/v1/sfc/corporations/{ce}/history` | `hk_sfc_history` | Only if retained history is allowed; observation chronology distinguished from source effective history |
| `GET /api/v1/sfc/status` | `hk_sfc_status` | Qualified/disabled modes, cohort coverage, accepted version, source hold, last success/check and freshness basis |

Names are proposed; final tool/request schema must make the licence-verification
purpose and constraints clear without treating self-attestation as permission.
Normal public reads use accepted observations. If qualified access is on-demand,
separate that budgeted network action explicitly, cache/coalesce only within allowed
TTL, validate CE before any request and prevent anonymous requests from exhausting
the daily tracked cohort budget. Apply existing abuse controls plus a small shared
verification admission limit; do not add accounts/billing to solve it. Disabled
search/history is absent from discovery and UI, with an honest capability status.

Add a source-specific `/sfc` verification page (or a clearly separated source view
within current companies UI if current navigation supports it). Journey: enter CE
-> permitted corporate result -> source status/activity particulars -> dated history
or downloads only where enabled. Show whether this is a past observation, source
daily cutoff or unknown freshness. Label archive licence/staff data separately.
Use exact copied values for field-level verification; no AI-generated licence
judgment or “safe broker” badge. The source status does not guarantee suitability.

## 5. Verification matrix

| Layer | Required evidence |
|---|---|
| Identity/type | CE normalisation and grammar, malformed/injection/Unicode lookalikes, person-versus-corporation response mismatch, regime/type discrimination, duplicate names with distinct CE, no inferred BRN join |
| Temporal/status | Unknown/null end dates, active/suspended/revoked/ceased source codes, future effective activity, multiple activity intervals, same-day correction, failed/missing response != revocation, EOD age != live status |
| Purpose/privacy | Mode matrix exercised at writer, reader, HTTP, MCP, discovery and export boundaries; no contacts/individual directories/raw payload leak, no unapproved history/cache retention; user purpose alone cannot unlock a mode |
| Collection | 25-record intent with multi-read requests, all request/retry/failure counts, cap partial batch, 304/429/403/timeout/HTML login page/oversize/schema drift, idempotent run/crash resume, source hold independent from CR/HKEX |
| Data pilot | Every selected CE and every accepted licence/activity/status field reconciled independently; excluded/unknown records and source cutoff recorded; original source evidence retained only as allowed |
| PostgreSQL/read | SELECT-only reader, writer isolation, supported migration combinations, source/version/filter-bound cursors, history retention expiry, concurrent publication and index/latency/output limits |
| Recovery/live | Fresh offsite dump/download/restore full cohort equality; live exact-CE and permitted history/search parity in REST/MCP/EN/繁中/browser; real permitted download contents; denied modes absent; old archive and other packs unaffected |
| Ordinary operation | Actual scheduled/qualified on-demand occurrence, last-check versus last-fact timestamps, safe source outage preserves accepted observation, backup failure closes growth, rollback to prior compatible source version |

Synthetic contract validators can be extended with isolated fabricated CE data;
they do not replace the authorised real cohort. Tests must assert expected source
facts, not simply serializer self-consistency. All shared mandatory checks still apply.

## 6. Release, rollback and done evidence

Use source-specific flags and rollback: suspend only SFC jobs/actions, retain prior
accepted SFC version, keep historical Webb and official CR modes working. A policy
restriction may require withholding affected output even if an old accepted version
exists; availability never overrides source rights. Document permitted retention
and deletion/backup implications with a reviewable procedure before activation.

Commit `docs/verification/sfc-<date>/` containing purpose/rights matrix, contract/
cohort specification, complete pilot checks, parser/PG/failure/security review and
fixes, exact test/CI receipts, PR/merge/adoption, actual live journeys/downloads,
source cutoff, schedule/ordinary-occurrence, offsite restore and rollback evidence.
The result may be a qualified verification service with directory/history/export
disabled if that is the allowed route; report those exclusions explicitly. A gated
connector or synthetic corpus is engineering completion only, not fresh SFC live
acceptance. Continue all unblocked work and present the smallest concrete source
decision for any unavoidable remainder.
