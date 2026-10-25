# Working private racing prototype

25 October 2026. The user clarified: build the working product first; do not make
obtaining a licence a blanket prerequisite for development. This supersedes the
prior plan's development stop at synthetic fixtures. It does not assert that a
licence exists or change production's public data modes.

## What now works

A standalone loopback-only process imports factual results from ordinary public
HKJC results pages. It serves an English/Traditional Chinese meeting/race explorer,
horse/jockey/trainer identities and their appearances within the imported meeting,
version-pinned REST and four MCP tools, a same-origin API reference and actual
CSV/JSON/checksum ZIP downloads. Reads use the local snapshot and never scrape.

The real pilot is **21 October 2026, Happy Valley: 9/9 result races, 104 result
rows, 18 successful bilingual captures**. Every race's horse IDs, jockey/trainer
IDs, placings/statuses, draw, exact time, carried/body weights and final published
win odds agree across the two languages. Metadata is observed on 25 October,
with source hashes and UTC capture times; it is not a contemporaneous odds feed.
No media, incident narratives or source HTML body is stored by the collector.

Actual source behavior fixed two gaps in the synthetic-only engineering:
Chinese labels contain line breaks, and a withdrawn standby horse can have no
horse number or draw. The parser accepts reordered known columns, preserves
withdrawal codes and missing values, and still rejects unknown layouts/codes.

[The pilot receipt](development/pilot-receipt.json) identifies the immutable private
snapshot. [Real TCP REST/MCP checks](development/local-rest-mcp.json) cover all
nine races and participant types. [The native browser ZIP](development/browser-download.json)
contains the selected race's thirteen rows with matching manifest hashes.
[Recovery/package/resume](development/recovery-resume-package.json) proves exact
all-fact equality after isolated local SQLite restore, packaged private assets,
and zero network calls when resuming an already completed import.

The browser checked first-Tab skip focus, no viewport overflow at the observed
desktop width, selecting the ninth race, the withdrawn participant, back navigation,
language change preserving that race, downloading its actual ZIP and the working
same-origin Swagger reference. Captured browser warnings/errors were empty. No
mobile-width browser verification is claimed for this prototype.

## Engineering verification

The 23 focused parser/store/private-API contracts passed. A complete required run
passed 520 Python tests (seven optional network skips), formatting/lint, real
PostgreSQL contracts for existing sources, and 113 Worker tests/type checks.
The final pushed commit additionally runs the mandatory pre-push hook and required
CI; see the linked pull request checks for that exact revision. Package inspection
confirmed all four private prototype assets/modules in the wheel, outside the
public assets namespace.

## Run locally

From the repository root after the normal locked environment setup:

```sh
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.curated.racing.prototype collect --date 2026-10-21 --venue HV
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.curated.racing.prototype serve --port 18844
```

Open `http://127.0.0.1:18844/`; REST reference is `/docs`, schema is `/openapi.json`
and MCP is `http://127.0.0.1:18844/mcp`. `--database PATH` before the subcommand
selects a separate private database. Collection can resume from its normalized
checkpoint; `collect --refresh` performs a bounded reread and creates a new immutable
version while retaining old versions. No collector runs on API/browser reads.

The CLI has no public-bind option: it binds `127.0.0.1`, disables proxy-header
trust, rejects non-loopback clients, unrecognized hosts and cross-origin browser
requests. Assets live inside the private module, outside the public assets tree.
The main production application never imports or mounts this server. The private
store is independent of production PostgreSQL, policies and accepted pointers;
its snapshot prefix cannot be mistaken for a licensed production data version.

Collection is single-session, fixed-route, past-meeting-only, bounded to 400 KiB
per response, 40 attempts/16 MiB/ten minutes per run and 200 attempts/64 MiB per UTC
day. Attempts reserve budget before HTTP; redirects, 403/429/503 and ambiguous
requests stop further collection and remain recorded across process/day changes.
An operator-only parser-correction reconciliation can settle the two known
completed-response parser errors using the reviewed parser file hash. It cannot
clear HTTP or unknown-request holds. A held/failed import never replaces a current
snapshot. Checksums detect modified local snapshots.

## Source evidence and remaining scope

[Renavon's terms](https://renavon.com/terms), checked today, say its information is
collected from publicly published HKJC and other Hong Kong sources, that it does
not redistribute a proprietary/licensed third-party feed, and that it claims no
rights over underlying public information. They do **not** establish whether a
separate HKJC agreement exists. Its subscription licence is its own customer-use
contract, not evidence of an HKJC grant. Conversely, [Racing Post's owner](https://www.spotlightsportsgroup.com/sports-betting-news/spotlight-sports-group-agrees-new-deal-with-hong-kong-jockey-club/)
publicly describes an HKJC agreement including racecards and other content. One
publisher's arrangement does not establish a universal development requirement.

Private development now proceeds independently of that unresolved licence question.
No provider enquiry was sent, feed bought, terms accepted, access control bypassed,
production schema/writer installed, source schedule activated or public factual
dataset enabled. Those decisions have not been silently inferred from this build.

This pilot reconciles the **results-page race inventory**, not a separate declared
runner inventory. It does not complete a season/history, full profiles, sectionals,
dividends, trials/rankings or a prospective series. These are visible implementation
and coverage tasks, rather than claims that this meeting proves the whole racing
track complete. Future public use should be assessed for its actual routes, facts
and output modes; this prototype does not decide a legal question by setting a flag.
