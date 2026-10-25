# Released UX repairs — 25 October 2026

The repaired journeys are deployed and observed at **https://mcp.hk**.
Implementation/review PRs: [67](https://github.com/heathermhuang/mcp-hk/pull/67),
[68](https://github.com/heathermhuang/mcp-hk/pull/68),
[69](https://github.com/heathermhuang/mcp-hk/pull/69).

## Exact adoption

| Component | Observed identity |
| --- | --- |
| Gateway/assets source | `790ae5172fab6c86944f7eabea54780b72f09deb` |
| Worker version, 100% | `337926a4-221e-41c9-b044-7dc4f05c683c` |
| Gateway container image | `sha256:af40c180c21004a9389978caac4961ac977ae4624e5efb2fa89b364d633b4f7c` |
| Private controller | Same source commit; `controllerContract=source-aware-ux-1`; `source-review-11`; accepted data ready |
| Curated backend source | `4f727da7eae2c1dc9068fee54107475572ad0529` (later changes do not alter curated reader code) |
| Curated backend image | `sha256:63bb32b5020c0a4aa3562ebb56f9dd70e4fbf2587f35cb2980c4ae9133ce54f3` |
| Running archive reader SHA-256 | `6aea9d3ff6212cc0604c8988231c90e9a3a74e23bbf2ebd683c18dd2847821d9` — matches merged source |
| Archive data | `enigma251227-hk-v1` |
| Official observation data | `official-8d70e15e57b12485adc5ea176daec66a` |

The initial upload exposed a real distinction between public asset/container
adoption and the controller environment. Its diagnostic still reported the prior
release, including after explicit flag-based reactivation. Resource review remained
paused. Configuring `durable_objects.code_update_strategy` as `{"mode":"immediate"}`
in the temporary four-schedule configuration, then activating the same verified
Worker version, produced the final controller contract and source commit. No lease,
Durable Object storage, quota state or accepted data was cleared. The earlier
receipts are retained locally; upload success alone was never treated as completion.

The curated service was built in a new immutable host release directory. Only its
read backend was replaced; PostgreSQL, proxy, owned source checkout, maintenance
units and data versions were preserved. Its grouped capability was qualified over
HTTPS before enabling the new consumer. Representative full-data prefix plans took
2.497–5.382 ms; bounded requests returned at most 20 identities and three name
examples. No schema/index/data migration was needed.

## Review and verification

Final required gate: **338 Python tests passed**, 30 expected skips (23 PostgreSQL
contracts run separately and seven optional network tests); **112 Worker/UI tests
passed**, plus formatting, lint, generated Worker types and TypeScript. Required CI
passed for Python 3.10/3.11/3.12, PostgreSQL, quality, deployment checks and the
rendered-browser workflow on the exact final head. All **23 PostgreSQL contracts**
passed, including restore, old/new contracts, source identity, aliases across pages,
signed cursors and actual HTTP/MCP parity.

Nine deterministic Chrome scenarios cover all 16 routes in both authored languages,
320px reflow and representative 390/768/1280px layouts, keyboard/focus/history,
late requests, partial company-source failure, private property state, plate modes,
consent and labelled workbook selection. These are browser fixtures, not live
provider evidence or an independent unfamiliar-user/screen-reader certification.

The final deployed runtime then passed seven real browser journeys:

1. Catalogue scope retention and a meaningful HKO weather bulletin.
2. The original rainfall GeoJSON with valid scalar projection, excluding geometry.
3. Grouped company identities, version-pinned names and a real page ZIP download.
4. Public building links, sale/rent filters and refresh restoration without query text.
5. Plate history and comparison modes with only honoured filters.
6. Nearby licences, radius changes and explicitly district-wide 2024 population.
7. Chinese mobile status and public guide/about/policy/reference routes.

There were no browser page exceptions. Independent ZIP inspection confirmed 20
unique organisations, the advertised source/version/scope and every member hash.
Live HTTP/MCP discovery exposed 36 tools and the new optional grouped contract;
archive and official grouping, legacy name-fact callers, disjoint cursor pages,
source-linked weather and the first statistics request passed.

Live holiday JSON returned five actual calendar event rows from a 51-event source,
with `scope=calendar_events` and `recordPath=vcalendar/0/vevent`; event dates and source
precision remain intact. The first displayed events are in 2025, not presented as
today's observations. The HKO JSON schema-drift limitation remains explicit; the
working bulletin alternative does not bypass that hold or raise response limits.

The fresh protocol pass caught an incorrect district-list shape in introductory
copy. PR 69 corrected it to the observed statistics response (`data.population`,
`data.referencePeriod`, `provenance`) and added a source-backed contract test. This
correction was deployed and retested. The consolidated final review has **no
blocking findings in the released application**.

## Acceptance map

| Scenarios | Result / evidence boundary |
| --- | --- |
| A01–A03 | Task discovery, scope, list/detail history and pagination verified in rendered browser; real scope/preview path observed. |
| A04–A05 | Real weather, safe rainfall projection and event rows observed; ambiguous/nested choices and workbook selection covered by deterministic contracts/browser. Byte cap unchanged. |
| A06–A08 | Real grouped identities, source separation, cursor continuity and independently verified export; PostgreSQL alias/leading-zero/version cases and browser partial failures passed. |
| A09–A11 | Real property, plate and neighbourhood journeys passed; privacy/filter/date/reference qualifications retained. |
| A12 | Remote MCP discovery and cited reads passed. Clean installed Codex/Claude Code/Cursor setup remains **pending**, labelled on the site; no copy/health result is called a connected client. |
| A13–A14 | Source-backed HTTP/records walkthroughs, corrected first-response shape, readable status and honest dates verified. |
| A15–A16 | Both locales, rendered roles/focus/keyboard and responsive reflow passed. No formal accessibility or independent-user usability certification claimed. |
| A17–A18 | Live initial consent/rejection produced zero optional requests and left search uncovered; GPC/DNT/withdrawal/redaction, retry, empty/failure and prior-result behavior covered by deterministic tests. |
| A19 | Public routes, legacy links, source-pinned machine contracts, Swagger/CSP and discovery checks passed. |
| A20 | Exact controller/backend adoption, accepted-pack readiness, all-five schedule restoration and fresh isolated recovery passed. |
| A21 | Preview observed one schema plus one record request; one bounded company search per requested source. Initial home requests remained 15. Three warm-load samples below; no claim of statistical performance improvement. |

## Recovery and schedules

Fresh accepted backup: `6604b58b90aa826892ae41f1569b98e9f087e472655f363b9d3ab8d6798bbcf9`,
63,007,757 bytes, created at **11:42:14 HKT**. The standard restore test passed. A
separate isolated restore additionally verified full SQLite integrity, inventory
`f8d8e9945a694617b6a2a9eb565e2a03`, **4,984 datasets**, **63,360 resources**,
**17,276 restaurant records** and **18 population records**. The archive and each
retained source capture were checksum-verified by the normal restore implementation.
This legacy checkpoint does not contain the separate curated PostgreSQL database.

Only resource cron was paused, for at least the documented 15-minute propagation
window and through actual adoption. All five checked-in schedules were restored:
backup, restaurants, weekly population, weekly catalogue and five-minute resource
review. Configuration restoration is observed; future scheduled occurrences are
not invented. Existing source/provider limits and the independent security branch's
qualification status are unchanged. A pre-existing failed official-address unit was
observed on the curated host and preserved; this read-UI release did not restart it
or claim to repair official ingestion operations.

Rollback targets remain the previous verified Worker version and image, with the
accepted checkpoint retained. Revert grouped consumers before rolling the optional
backend back. No frontend rollback requires deleting/restoring the live data database.

## Assets, consent and performance

Eighteen assets/pages were checked against exact local source hashes. HTML on the
custom domain includes an existing zone-injected Cloudflare beacon; the production
CSP blocks it. The original operator-origin HTML matched exactly, and custom-domain
HTML matched after removing only that identified blocked injection. A real browser
confirmed **zero optional requests before consent/rejection**. No account/zone
analytics setting was changed to hide the mismatch.

Homepage initial requests: **15 before and after**. Three warm-load samples were
129.3/140.1/158.6 ms before and 130.6/132.8/149.8 ms after (same browser, one network
vantage point). Warm transfer increased from 10,833 to 11,280 bytes. Nine selected
source assets grew by 6,838 gzip bytes in total; no frontend framework/runtime was
added. These are bounded samples, not a web-performance SLA or causal speedup claim.

Machine-readable receipts are in [released/](released/). The pre-release plan and
review remain historical records. The pending installed-client matrix and absence
of independent-user certification are explicit limitations, not silently passed gates.
