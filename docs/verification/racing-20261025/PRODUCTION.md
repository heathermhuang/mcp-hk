# Racing production pipeline

The owner directed end-to-end implementation and explicitly removed a licence
prerequisite. The operational basis is ordinary HKJC public factual results.
This is an implementation/use decision, not a representation that HKJC endorsed
mcp.hk. No provider outreach, purchase, agreement acceptance, betting account,
media replication or access-control bypass is part of the pipeline.

## Architecture and acceptance boundary

Promote the tested real-results collector into the existing SQLite service and
R2 recovery path. Racing uses its own `racing_*` tables and accepted pointers;
existing government snapshots, CR/Enigma and Webb pointers are preserved. The
unused PostgreSQL racing engineering remains independent and is not provisioned
as a new production dependency. No new infrastructure is created.

Public `/racing`, REST and MCP read only accepted stored snapshots. Every meeting
and race is pinned to an immutable `racing-results-v1-<sha256>` version. Sharing,
language changes and downloads preserve that version. Old versions remain
readable. ZIP files contain JSON, formula-safe CSV, attribution and file hashes.
Participant views cover identity and appearances within the selected imported
meeting; they do not pretend to be full historical profiles.

A publication has these steps:

1. Validate the complete results-page race inventory, identities, exact units,
   result/withdrawal codes, bilingual facts, capture hashes and explicit coverage.
2. Stage the source snapshot; public accepted pointers stay unchanged.
3. Save the complete current service checkpoint in existing private R2.
4. The container downloads that exact R2 object over its fixed authenticated
   bootstrap route, checks its SHA256 and safe restore bounds, restores to a
   separate temporary SQLite file and compares every racing fact/control table.
5. Only a matching restore advances that meeting's racing pointer. Save another
   checkpoint containing its accepted pointer and recovery proof.

Failed or superseded candidates cannot replace accepted facts. The independent
operator's post-deploy offsite-download/restore and live HTTP/MCP/browser checks
are still required release evidence. A static release header alone is not proof
of controller/container adoption.

## Collection and durability

Only authenticated operator actions and the existing five-minute maintenance job
collect. Public queries never fetch HKJC. Fixed results/fixture routes, one source
session, 400 KiB/page, 40 attempts/16 MiB/ten minutes per batch and 200 attempts /
64 MiB per UTC day bound collection. These are engineering ceilings, not claims
about provider-approved quotas.

Production reserves each attempt in the existing Durable Object **before** its
HTTP request. These counters, unresolved requests and holds survive loss of the
ephemeral data container. Imported local receipts seed the same ledger
idempotently. SQLite keeps the corresponding source audit and checkpoints.
Provider-denial/unknown holds cannot be reviewed as parser corrections. A known
completed-response parser correction requires the deployed transform checksum and
retains its request charge. Collector/storage work runs outside the async reader
loop; public racing queries share four bounded slots.

The official fixture calendar supplies dates and venues. Programme counts are not
silently treated as actual results counts; no-programme/cancelled entries are
retained as exceptions. Backfill queues checkpoint between requests. Daily
calendar checks discover completed meetings; only the two latest accepted
meetings within fourteen days are reread for amendments. A persisted refresh
cutoff prevents mixing stale Chinese pages with new English pages. Unchanged
checks stop after the bounded comparison. No model runs on a schedule.

The initial real fixtures include Happy Valley 21 October (9 races, 104 rows) and
Sha Tin 19 October (11 races, 146 rows), and completed Sha Tin 25 October
(11 races, 142 rows): 31 races and 392 published rows in total. Current-day data must pass the
same all-race checks. Blank source placings are `not_reported`, not fabricated
withdrawals or zeros. The official special-incidents glossary qualifies the
finite known codes; unknown nonempty codes still stop the affected import.

## Release and operator commands

Use the existing shared release slot and `docs/production.md`: pause only the
resource cron, preserve the other four triggers, wait fifteen-minute propagation
and the actual maintenance/seed lease, merge/deploy the checked source, verify
actual controller and `healthz.racingPipeline=results-r2-v1` adoption, then ingest
and verify. Restore all five schedules before releasing the owned slot.

`POST /__ops/racing` is authenticated at the edge and container and serialized by
the existing maintenance/seed lease. Its bounded JSON actions are:

- `import`: `{snapshot,pages,attempts}` from the verified local collector; source
  data is imported only into racing tables and does not replace the service DB.
- `calendar`: numeric `year` and `month`; capture the official fixture inventory.
- `enqueue`: bounded `{date,venue}` entries; optional explicit recent-range refresh.
- `advance`: one bounded backfill batch; persistent source limits/holds apply.
- `reconcile_parser`: exact recorded attempt and reviewed transform SHA256; never
  clears an HTTP/unknown hold.

`POST /__ops/run?pack=racing` advances/checkpoints the same queue. Ordinary resource
maintenance performs one racing step and preserves other pack behavior. Racing
operator imports alone have a 16 MiB authenticated body allowance; public HTTP/MCP
remain capped at 64 KiB. No operator credential belongs in Git, URLs or logs.

## Coverage is explicit

A working end-to-end results path is distinct from complete data-family coverage.
Results-page inventory does not establish independently reconciled declarations.
Full seasons/history, full profiles, sectionals/dividends, trials/rankings and
prospective odds/pool/change series must report actual collected ranges and gaps.
No historical intraday odds or full vendor parity is inferred. Backfill can remain
in progress under the durable daily budget; accepted data stays usable throughout.
