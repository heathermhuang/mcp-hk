# Archive-route repair: production verification

The archive-route repair is released and verified. The four-dataset programme is
still **incomplete**. Evidence is pinned in
[racing-archive-live-release-20261027.json](racing-archive-live-release-20261027.json).

PR #105 merged as `8ebe763e96d2dc2f213f81de725356e1be7f6a3a`, with the identical
tree of checked head `5bd003ad5382d2f8a4665ee92552b4d6ff8a3aa1`. The required
hook passed 675 Python tests, seven optional live skips and 145 Worker tests;
all seven required CI gates passed. Worker version
`f9bdd6f6-595c-4057-81de-84ca4d6a4c69` and the actual controller adopted the
merge. The unchanged private backend remains on `3aeaaafbd7f51636c314e707de82911c48567632`.

The original 302 was reconciled only after both settled diagnostic receipts and
the exact archive Location hash matched. Its original error and conservative
409,600-byte charge remain. The three requests to the original URL are retained:
the original attempt and two diagnostics. Reconciliation dispatched zero provider
requests and resumed exactly one matching and 52 globally blocked queue entries.
It did not erase other failures or count the redirect as obtained results.

The collector then refreshed fixture inventory, the two recent meetings and two
dated profile observations through its existing fairness order. Each completed
checkpoint was independently restored before continuing. The previously held
15 July 2026 Happy Valley meeting then passed bilingual source reconciliation,
actual offsite download/restore and publication: nine races and 107 result rows.
Its accepted version is
`racing-results-v1-7338db3c7faf9638cbb6c736d67c8c2cf6bb660d7914c39297cdb62ed913bede`.

The final accepted checkpoint
`82b83c48f1e01dbf4542e4261bced3b7f6fbe5f6e91b0ece128b318f50593bfe`
was independently downloaded and restored: all 15 Racing tables, all 14 prior
accepted meeting versions and the original three profile facts were retained.
Every target race matched that restore through live REST and MCP. The pinned
previous latest meeting also remained readable during collection, with its full
envelope matching the restored baseline.

The browser passed 22 actual journeys and ZIP downloads: every race in English and
Traditional Chinese at 320px, plus first/last races at 1280px. Rendered participant
names, every JSON fact, every CSV cell and all manifest member hashes matched.
There were no page errors, root overflow or browser requests to the provider.
Results ZIPs currently contain JSON, CSV, notice and manifest; there is no separate
`schema.json` member. These are neutral release checks, not customer adoption.

At the post-target checkpoint (21:52 UTC, 26 October), coverage was 15 meetings,
147 races and 1,840 rows, including 14 recent meetings and this one historical
meeting. Five dated profiles were accepted. The durable budget was 193/200 reads
and 37,535,516/67,108,864 bytes, with no unresolved request or source hold. Redirects
and their target reads were charged separately. Subsequent scheduled work can
change those counters and coverage.

All five schedules were restored and read back; leases were free and the owned
release slot was released at 21:55 UTC. Wider historical coverage, declarations,
remaining Racing families, whole profile-cohort/career coverage and ordinary
trigger provenance remain separate acceptance items. Company daily RPO, fresh
SFC serving and the full HKEX filing window also remain incomplete.
