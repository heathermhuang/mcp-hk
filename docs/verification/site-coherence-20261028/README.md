# Bilingual website coherence — 28 October 2026

The live-site audit found missing family entry points, incomplete connected search,
conflicting availability wording and separate racing language/navigation behaviour.
The existing dark/mint identity, public URLs and all source controls are retained.

`web/datasets.json` is the shared bilingual content registry for the homepage,
`/datasets`, explorer context and connected-query discovery. It covers official
companies, Webb organisations, SFC archive, HKEX summaries, Webb disclosures, racing,
addresses, restaurant licences, district statistics, Plate.hk, SeeHouse, transport
and the wider government catalogue. Source-specific status owns changing counts,
versions, coverage and update outcomes; the registry carries no frozen row counts.

Primary navigation is Find data → Connect AI → Guides → Data status. Find data opens
the family directory; `/coverage` remains the searchable catalogue. Each family
uses question, available view, limitations, dates, download scope, explorer, status
and HTTP/MCP example. Existing deep links remain valid, including fragments and
query parameters during language changes. SFC and both HKEX read views appear in
connected search only under their existing backend/feature configuration.

HKEX says published summaries rather than promising current data, retains the
source-hold warning and keeps full-filing qualification visible. SFC is labelled
as an archive with separate unactivated official observations. Racing shares the
footer, translated controls and locale-preserving navigation; an empty meeting or
result list cannot promise an import or imply that no racing occurred. Source
status links to each view's actual status rather than inventing a failed read for
interfaces whose availability is checked on query. API reference introductory copy
is translated; operation names and source fields retain original language.

Verification includes the existing API/MCP/database/restore/Worker suites and the
existing explorer browser regressions. The new `content-browser.mjs` checks all 20
page surfaces in both languages at 320/390/768/1280px (160 cases), shared navigation,
family links, gated SFC controls, locale and horizontal overflow. Fixture journeys
are engineering evidence, not provider qualification. Review found no remaining
blocking issue after correcting fragment locale links and data-status names.

This release does not collect source data, enable SFC, retry the consumed HKEX
diagnostic, clear SOURCE_ACCESS_HOLD, alter quotas, add schedules, or complete the
dataset programme. Company publication/recovery and the selected SFC cohort retain
their current ownership and gates. Production release and refreshed live/download/
restore receipts are retained in the parent workspace's
`research/mcp-hk-site-coherence-20261028/` report.
