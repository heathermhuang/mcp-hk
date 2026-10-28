# Bounded acceptance and source engineering

28 October 2026. Programme INCOMPLETE. This release grants no source permission,
cohort, credential, hold exception or ordinary-operation qualification.

## Existing owners and deterministic work

The active `verify-company-daily-publication-and-recovery` follow-up remains in chat
`01a16dec-cb5d-74e3-861e-d831059f5a47`, daily 13:40 Singapore/Hong Kong time. All its
requirements remain. No duplicate crawler, timer, model loop or owner message was
created. Source publication/offsite remain 13:00/13:17. The owner first uses its
existing `official_backfill_checkpoint`. The optional compact comparison is:

```sh
PYTHONPATH=src python -m mcp_open_data_hk.curated.qualification_checkpoint --folder <private-checkpoint-folder> --source company
```

It performs one bounded company status read (or four source status reads when no source is selected), zero provider reads, excludes
heartbeat/resource clocks, saves immutable changed receipts, and emits nothing
when unchanged. It does not pass acceptance or repeat failed source actions.

After an actual normal full publication, obtain fresh SELECT-only
`curated.official_acceptance` output. Both runners reject a partial/staged or
changed original 94-pair/188-key inventory before public requests:

```sh
PYTHONPATH=src python -m mcp_open_data_hk.curated.company_verify --cohort <actual-cohort.json> --folder <shared-progress-folder> --limit 4
PYTHONPATH=src python -m mcp_open_data_hk.curated.company_browser_verify --cohort <actual-cohort.json> --folder <shared-progress-folder> --limit 2
```

Use the same checkout, cohort and shared folder. Only the existing owner should
run them. The SQLite journal serializes batches, pins version/inventory/expected
facts, retains failed and unknown attempts, and resumes unattempted cells only.
An investigated correction may explicitly reopen a failed cell with a checked
release and review-evidence hash; the old attempt remains. A changed cohort/version
requires another journal and all version-dependent evidence again. All 1,128
required source/interface/language cells remain required; API completion alone
never completes browser or ZIP steps. Supplemental leading-zero, multirow,
pagination and accepted recovery/RPO/performance requirements remain additional.
The prepared supplemental case is `cr:local:05243897` in the parent research folder.

REST/MCP work is serialized at 2.1 seconds/request and bounded by batch/time/body.
HTTP failure, quota response or interrupted dispatch stops without retry. The
browser runner launches a dedicated visible Chromium window, uses actual page
responses and visible download actions, saves actual ZIP bytes and full captured
responses, and verifies exact source fact/lineage, version, language, page scope,
JSON, all decoded CSV values and every manifest member hash/size. It never mocks
production. Synthetic rendered regressions have their own clearly labelled script
and receipts; they are not live acceptance. Existing public aggregate quotas still
apply; no runner owns a fresh allowance or may compete with another owner.

Company search now accepts an explicit official version through REST, MCP, private
reader and explorer, rejecting a different cursor version. Existing callers keep
their default behavior. The explorer's selected-observations ZIP contains the full
detail envelope and nested source facts; search-page ZIPs remain separate. It keeps
the at-most-100-observations scope, never a whole-registry export claim.

## Racing

The single existing five-minute step and shared 200/day allowance are unchanged.
One bounded planner adds at most one missing-dividend meeting to the existing
queue, with original-season priority. Existing refreshes, source holds, unknown
requests and staged recovery take precedence. It never changes an accepted pointer
or dispatches a read. Each meeting/parser is attempted once; an explicit refresh
already exercises that parser and counts, so the existing July 15 HV refresh is
not duplicated. A still-missing table after this pass needs changed source/parser
evidence, not blind recapture. Accepted versions advance through existing recovery.

`curated.racing.families` adds offline contracts for independent declarations,
career inventories, ordered distance/precision-reconciled sectionals, trials,
period/metric/unit rankings, jackpots and prospective markets. Withdrawn, scratched,
reserve, missing and unreported states remain distinct; trial running order is not
placing; source ranks and historic ticks are not inferred. These are normalized
contracts, **not real qualified parsers**. Public status now names the exact
capture/inventory/dictionary/policy evidence missing for every unfinished family.
No new route is enabled. Complete provider parsers still need actual qualified
captures/routes; the empty/unknown family grants do not authorize guessed routes.
Narrative output and Mark Six remain separate, with Mark Six excluded.

## HKEX

The exact held diagnostic, its implementation and required separate decision are
in HKEX-EXACT-HOLD-EXCEPTION.md. Ordinary admission remains closed; no diagnostic
is dispatched without the actual human exception. It uses the shared durable
quota, original-response identity and single-use approval hash, no-follow transport
and sanitized metadata, preserving the hold and failed/unknown charge.

The one-document Form 3B proof, 145-target audit, five DION reachability results,
stock-code correction and all issuer/date/channel/revision uncertainties remain.
No inventory source is guessed from event-date navigation or daily summaries.
A complete one-issuer/seven-day filing-date inventory and remaining forms require
qualified listing/capture evidence; the held route is not bypassed for engineering.

## SFC

The actual cohort/purpose/output decisions remain required. Production has no
source policy/version/attempt, source writer/uploader credential or timer. The
new SELECT-only reader SQL is a NOLOGIN review packet, not executed. Existing
writer/uploader/runtime approval requirements are preserved.

`curated.sfc.artifacts` prebuilds a deterministic bounded 2-MiB ZIP from all facts
of a complete accepted tracked cohort, through an actual SELECT-only reader. It
requires actual source format, same-policy facts, and the independently restored
accepted pointer, not just a candidate. The operator command is
`python -m mcp_open_data_hk.curated.sfc build-export --version <accepted> --folder <protected-directory>`
with a source-only `SFC_READER_DSN` and the checksum-pinned policy. The artifact
has full JSON, spreadsheet-safe CSV, schema, provenance, notice and member hashes.
It refuses overwriting a prior build.

Private/public REST and gated MCP deliver already built bytes, never a SQL export
or source fetch. Configure only the reviewed protected
`MCP_HK_SFC_EXPORT_DIRECTORY` on the backend with a read-only mount; it is absent
in production. Fresh policy/version/expiry checks and file hashes apply on every
delivery. Revocation/expiry withholds copies. The browser offers the same-version
cohort download only when the backend has a verified artifact and the gateway
adopts its independent export policy. Disabled modes remain absent from discovery.

`curated.sfc.retention` measures capacity against existing shared allocations,
20-GiB disk/1-GiB memory reserves, dump/restore/WAL/index/export peaks and the
512-MiB local bound. Physical-expiry proofs enumerate database/captures, local and
retrieved dumps, fact-bearing receipts, R2 immutable/latest copies, interrupted
copies and exports. They require exact approved fabricated canaries and actual
physical-absence observations within the permitted duration. Read denial, lifecycle
configuration or expiry metadata alone cannot qualify deletion. The module deletes
nothing. A real approved canary execution/configuration and source-specific
retention policy remain pending, along with real source/public/ordinary operation.

The new offline HKEX inventory verifier reconciles every explicitly in-scope form
and page against the same source snapshot/total and exact issuer/channel/window,
requires actual filing-date fields, and rejects absent revision targets. It cannot
turn Form 3B event-date navigation, a document or an unqualified identity assertion
into a real inventory. No production listing adapter/source evidence is supplied
by this verifier; the corresponding acceptance gates remain open.

For a complete qualification wake, prefer the deterministic coordinator:

```sh
PYTHONPATH=src python -m mcp_open_data_hk.curated.company_suite --cohort <actual-cohort.json> --folder <shared-progress-folder> --seconds 5400
```

It runs successive serialized batches of at most 20 steps, each with a 580-second
work window and bounded request/browser deadlines, within one finite 90-minute
public-read session. It saves each step before continuing and stops on the first
new failure. It creates no schedule and invokes no model. Reuse the same journal
to resume a timed-out session. Running only one tiny batch on each daily wake
could exceed the version-retention window; this coordinator lets the existing
owner complete the matrix within a single pinned-version wake when quotas and
service availability permit. A timeout/failed/unknown cell is still pending.

Operator HTTP verification and the exceptional HKEX inspection also have absolute
POSIX deadlines, beyond per-I/O timeouts, so a slow trickle cannot extend a batch
indefinitely. Expiry preserves the journal/request reservation as failed/unknown;
there is no automatic retry or hold clearing. These CLIs already require POSIX
file locks and run on the existing macOS/Linux operator and host environments.

## Company operator quota feedback repair

Full-cohort verification encountered a real per-client minute admission failure.
The operator helpers now share pacing state between Python REST/MCP and every
visible browser process. Server-reported headroom of ten remaining requests or
fewer defers the next request until the reported reset; HTTP 429 retains its
Retry-After admission and original failure response without automatic retry.
A day-long hold stops the bounded batch instead of blocking indefinitely. The
service quotas and all 1,128 assertions are unchanged. Prior passing cells remain
valid; failed cells require the existing explicit review/reopen procedure. This
operator-only correction changes no serving source, Worker, container or timer.

The first admission repair exposed a request-lifecycle bug during live validation:
a response-event waiter could remain pending when a routed request failed without
an HTTP response, then reject outside the journey's error handling. The follow-up
uses the request-owned `response()` result, retains network/deadline failures,
and signals the journey without automatic retries. A real local Chromium fixture
covers cancellation, actual HTTP 429 and a never-responding request in rendered CI.
These are engineering regressions, never substitutes for the full live matrix.
Reference: https://playwright.dev/docs/api/class-request#request-response.
