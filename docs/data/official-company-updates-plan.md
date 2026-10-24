# P6: maintained official company observations

Source qualification checked 24 October 2026. P7 SFC/HKEX is excluded.

## Source and coverage contract

- Companies Registry / DATA.GOV.HK weekly catalogue:
  https://data.gov.hk/en-data/dataset/hk-cr-crdata-list-newly-registered-companies-2526
  lists 188 CSV resources (local and non-Hong Kong), from the week beginning
  30 December 2024 through 12–18 October 2026 at inspection. Daily discovery;
  retain actual ingested weeks separately from discovered coverage. Local files
  combine incorporation/re-domiciliation dates: do not guess which event occurred.
  Preserve that combined type. Non-Hong Kong language aliases can repeat Seq/BRN.
- Exact BRN address API, documented by
  https://www.cr.gov.hk/datagovhk/dict/data_dictionary_RO_PPB_en.docx and
  https://data.gov.hk/en-data/dataset/hk-cr-crdata-list-addr . Fixed local/foreign
  hosts and validated Brn/equal parameters only. Daily source, bounded tracked
  subset, no reader-triggered crawling. An empty response is no observation,
  never dissolution or deletion of an accepted address.
- Four monthly money-lender CSV/XLS registers:
  https://data.gov.hk/en-data/dataset/hk-cr-crdata-list-ml-licensees . All inspected
  files say `As at 30 September 2026`; HTTP Last-Modified is 16 October 2026.
  Daily hash checks do not make monthly facts daily. Preserve MLR_No and licence
  number independently. No BRN is supplied, so no name-based company crosswalk.
- No qualified machine-readable company-level dissolution feed was identified.
  Statistical counts are not entity events. Gazette notice extraction needs its
  own source/parser qualification; P6 must disclose this unsupported coverage.
- Government/DATA.GOV.HK terms permit download, redistribution and commercial
  reuse subject to attribution and their conditions:
  https://data.gov.hk/en/terms-and-conditions . Retain source links, raw fields,
  capture hashes and terms in every official response/export. Attribution:
  Government of the HKSAR / Companies Registry / DATA.GOV.HK. These terms do not
  replace the original Webb archive notice.

## Identifiers, model and publication

Keep immutable Enigma release `enigma251227-hk-v1` unchanged. Store official data
in separate `curated.official_*` PostgreSQL tables on the existing dedicated host;
no additional provider or recurring expenditure. BRNs retain exact text and register
namespaces `cr:local:BRN` / `cr:foreign:BRN`; money-lender identities use `cr:mlr:ID`.
No invented CRN/BRN mapping, name matching, ownership or current officer claims.
Expose `view=latest_observed` on existing company search/get contracts; numeric
Webb entity reads remain archival. Official detail contains source observations
with event types, raw dates and day precision, rather than overwriting history.
Keep official and archival results visibly distinct in the bilingual explorer.

Immutable content-addressed captures include raw CSV/JSON and independently read
XLS verification bytes, fetch time, HTTP source modification time, actual week or
monthly cutoff, counts and validation evidence. Accepted versions map source keys
to verified captures; promotion is one transaction after all selected reads pass.
A failed/empty/partial read records a failed run and retains the accepted pointer.
Each rejected address is recorded as a gap and retains its previous observation;
independent qualified weekly/lender sources may publish with explicit address gaps.
XLS numeric identifier cells lose zero padding; their numeric comparison does not
alter the authoritative CSV identifier text or join identities. Search
and detail pin signed pagination and version; previous versions remain queryable.
Rollback moves only the official pointer to a retained qualified version.

## Bounded ordinary scheduler

A host systemd timer runs daily at 05:00 UTC (13:00 Hong Kong/Singapore), with
persistent catch-up, one writer advisory lock and a 15-minute service deadline.
Per run: one weekly catalogue, latest two local/foreign week pairs plus one older
uncollected week pair (at most six CSVs and six independent XLSs), four money-lender
CSV/XLS pairs, and at most 20 exact tracked address reads, serial per source host.
Hard request/byte/deadline bounds prevent sweeps. The oldest outstanding discovered
week is backfilled each successful day. A changed discovery list is not proof that
old already ingested files are rechecked: only the latest two weeks are revalidated.
Future runs are not claimed as observed. Expose discovered/accepted file counts,
missing weeks, subset address counts/denominator, last run success/failure and next
configured schedule. Retain unknown source publication times; measure fetch delay
from covered-through date and HTTP Last-Modified lag as a labelled proxy, not an
invented publication timestamp. Alerts are existing service logs/status receipts.

## Acceptance and release

1. Fixtures cover both weekly header generations, Unicode/aliases/leading zeros,
   combined events, all four lender schemas, malformed/partial/truncated reads,
   no-match/wrong-BRN address reads, XLS/CSV semantic/count disagreement.
2. Real PostgreSQL contracts cover idempotence, exact-key joins, signed version
   pagination across promotion/rollback, failures retaining accepted data, safe
   serving role, independent restore including captures/receipts/accepted pointer.
3. Real bounded source run publishes observed counts and measured source dates.
4. Required Python matrix/lint/Worker/DB CI, review and exact-head pre-push checks.
5. Merge and deploy following existing resource-cron pause/adoption instructions;
   preserve all five gateway schedules. Install/inspect the separate host timer,
   execute one real bounded production run, verify its receipt and next schedule.
6. Create daily local logical backups (30-day retention), covered by the existing
   provider weekly host snapshot policy. Copy a fresh release backup to existing private R2; retrieve, hash and restore
   into a fresh database, compare captures/rows/versions and query restored data.
   Verify live REST/MCP parity and English/Chinese desktop/mobile journeys and page
   exports. Existing complete archival downloads retain their unchanged scope.

Mutable-source guard: a weekly file with fewer rows than its accepted counterpart,
a lender snapshot falling below 80% of the previously accepted count, or a backward
coverage date is quarantined. A legitimate large source correction needs a separate
review rather than silently replacing accepted coverage. CSV/XLS agreement checks
all rows and columns, not just byte/row counts. A missing address does not apply
this deletion logic: its accepted observation remains in the version membership.
