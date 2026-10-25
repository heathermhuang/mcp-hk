# Build-first SFC implementation — 25 October 2026

The user's latest instruction is to build first rather than wait for a licence
or provider enquiry. The earlier permission-enquiry workflow is deferred. No
message, subscription, paid licence or new contract is needed for this build.
This supersedes treating the earlier UNSENT request as an engineering dependency;
it does not silently change the dates or source of historical records.

## Webb already had the foundation

The original Webb release includes SFC collection software and history. Our prior
source audit restored **13,446 corporate/activity intervals** (`olicrec`) and
**565,646 individual/firm/activity/role intervals** (`licrec`); these are interval
rows, not distinct firms or people. Existing production company/licence tools
already serve the attributed historical projection.

Webb's [original SFC.vb](https://drive.google.com/file/d/1uTrm05tT0epYNoSt-W2fGybvq3GeIraF/view)
uses the official corporate `/publicregWeb/corp/<CE>/licences` page, extracts
`licRecordData`, distinguishes `lcType`, and reads `regulatedActivity.actType`
with `effectivePeriodList.effectiveDate/endDate`. It also ran representative/RO
updates; this build retains the agreed corporate-only fresh-source scope.
[The original notice](../../../src/mcp_open_data_hk/webb-site-NOTICE.txt) makes the
released datasets and software available under CC-BY with attribution, including
commercial reuse. This build requires no Renavon subscription.

## Concrete implementation

- A real HTML/embedded-JSON parser, grounded in the released collector and the
  current public-register application. It validates corporate header, exact CE,
  SFO type and complete bounded licence intervals; no JS execution, person/RI
  fallback, contacts or inferred BRNs.
- Original date strings and parsed day values are retained together. The source's
  1-Apr-2003 SFO boundary stays visible; it is not silently erased as the legacy
  collector did and is not claimed as an original pre-SFO licence start.
- Missing overall/interval status stays `not_supplied`. The activity catalogue's
  `status` field is not relabelled as a corporation's licensing status. Null end
  dates, no match, login/denial, missing data and parse errors imply no revocation.
- A sequential operator collector with fixed HTTPS origin/routes, no redirects or
  proxies, a whole-response deadline, body bounds, durable reservation before
  each read, persisted 403/Retry-After holds, occurrence idempotency and failure-safe
  full-cohort staging. No public request invokes collection. Existing source-mode,
  exact-cohort, retention and publication configuration remains independent.
  A `connector_development` purpose supports private engineering without claiming
  intended dealings or a provider grant; it cannot enable public outputs/history.
- Raw-source checksums, exact capture routes and transform identity accompany the
  normalized facts; raw HTML is not retained by the collector. Restore qualification
  and publication also bind the version manifest, including this lineage.
- A working bilingual `/sfc` archive lookup uses the existing public company API:
  exact CE -> archived organisation -> version-pinned corporate activity intervals.
  Empty/error/unknown dates remain honest; failed reads retain labelled prior results.
  Official-source controls are a distinct section. Archive results are not current
  verification and do not initiate upstream reads.

## Development observation and tests

One bounded internal development read used an exact CE already present in our
Webb archive. The 21,035-byte licence page matched the legacy `licRecordData`
protocol and parsed all five declared source intervals. Its raw checksum was
`e3262ec6d17793829b5bdf7333cca43d349dacf81da70c83b7e376687e6fd3e4`.
Raw source bytes from interface inspection remain in ignored private development storage. This small read
proves the interface/parser path; it is not a register-wide coverage, current-status,
public redistribution, daily-update or full 25-corporation acceptance claim.

Synthetic raw-page fixtures independently test type/CE/date/schema/duplicate-packet
failure, contact exclusion and no-result semantics. Real PostgreSQL tests exercise
HTTP transport -> parser -> reservation -> source lineage -> validated candidate,
including idempotency and 403/429/304/redirect/login/oversize failures. Existing
restore/rollback tests remain mandatory. Rendered browser tests exercise the
functional archive page in both languages and mobile/desktop layouts.

## Run the build

Replay a saved page without a network connection, database or licence purchase:

```sh
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.curated.sfc parse \
  --html /absolute/private/corporate-licences.html --ce ABC123 \
  --observed-at 2026-10-25T00:00:00Z
```

The operator collector uses an existing source-scoped writer and checksum-pinned
technical policy for exact CEs/route/retention/budgets. It stages but never publishes:

```sh
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.curated.sfc collect \
  --policy-sha256 <active-policy-sha256> --scheduled-for 2026-10-25T00:00:00Z \
  --ce ABC123
```

`SFC_WRITER_DSN` is supplied privately, never as an argument or public request.
The fixed route template is `https://apps.sfc.hk/publicregWeb/corp/{ce}/licences`.
An unknown policy cannot enable public fresh results. The build proceeds using
Webb's existing grant and internal development evidence; a paid-feed/licence
purchase or unsolicited provider outreach is not part of this work.


## Real private collector run

The complete implemented collector was subsequently run for one exact archived CE
under the explicit `connector_development` purpose, with **one source read allowed**
and every public output mode denied. It fetched the actual official page, parsed
and staged all five expected activity intervals, reconciled the supplied dates,
then made a physical backup and restored it into a second isolated PostgreSQL DB.
All ten source tables and all facts matched. No accepted/public pointer was created.
Both disposable databases and the development dump were removed after proof.
See [the source-free aggregate receipt](real-pipeline.json). This is an internal
working-build observation, not an unattended job or a public fresh-feed launch.
