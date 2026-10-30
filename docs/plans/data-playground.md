# mcp.hk data playground — product and engineering plan

Preserved planning snapshot. Local implementation and verification are tracked in
[the candidate evidence](../verification/playground-20261029/README.md); the original
proposal status and historical planning receipts below are retained.

Updated: 2026-10-29. Supersedes `mcp-hk-data-playground.md` as the working plan.
Status: Proposed plan; no feature code, deployment or usability validation completed.
Evidence: refreshed `origin/main` and local checkout both resolve to `8504d79`.
Source paths below are relative to `work/mcp-hk-directory-20261029/`; backend
filenames and `web/` paths are under `src/mcp_open_data_hk/` unless prefixed otherwise.

## 1. Product decision

Build a public workspace where someone can discover a subject, open real data,
manipulate it, understand its limits and take away a useful result without learning
an API or provider file structure. Replacing JSON fields with dropdowns is insufficient:
people also need useful starting points, comprehensible columns, meaningful views,
and a way to share what they found.

**One workspace, with controls and views that follow the dataset's actual capabilities.**
Universal means consistent entry, exploration and source understanding across all
dataset families. It does not mean identical controls or guaranteed structured access
to every catalogue resource. Documents, live lookups and company histories need different
presentations inside that workspace.

Primary audience: residents, students, journalists and researchers comfortable with
search and basic spreadsheet filters but unfamiliar with APIs. These are intended
audiences, not observed adoption claims. The core loop is:

**Discover → open → narrow → inspect → share/download.**

Use a visual explorer first. An optional future assistant must produce the same
visible editable query and cited result. Avoid making a model call necessary to browse.

## 2. Corrections to the initial plan

| Initial weakness | Revised decision |
|---|---|
| Every dataset treated as a table | Shared shell and state; table, lookup, entity/history and document modes. |
| Schema assumed sufficient for generated filters | Prove exact numeric filtering/display before exposing it; schema currently collapses int/float. |
| Querying on every interaction | Draft/apply separation; current generic queries scan the resource. |
| Existing export assumed reusable wholesale | Reuse pure byte helpers; retain source-specific permission and notice checks. |
| Charts deferred entirely | Include a small loaded-page chart in the first vertical slice to prove exploration beyond browsing. |
| A new HTML page assumed sufficient | Integrate generated bilingual Worker/Python routes, discovery actions and metadata. |
| Universal label before family adapters | Scoped preview first; family-wide completion requires the entire inventory checklist. |

## 3. Evidence and uncertainty

| Premise | Receipt | Verdict |
|---|---|---|
| Filters currently require JSON | `web/coverage.html:10` | Confirmed; no user sessions supplied. |
| Generic query offers equality/projection/paging, no contains/range/global sort | `resource_api.py:24-31`, `resources.py:1010-1066` | Confirmed. |
| Equality distinguishes Python int, float, bool, string, null and missing | `resources.py:1050-1054`; ResourceQuery parsing probe | Confirmed: `1`, `1.0`, `true`, `"001"`, null retain distinct backend types. |
| Schema number metadata collapses int/float | `resource_formats.py:460-477` | Confirmed; missingCount also combines absent and null. |
| Each generic query scans all rows to count matches | `resources.py:1047-1066` | Confirmed; to_thread at `1102` avoids blocking the loop, not CPU consumption. |
| Continuation pins content version and rejects drift | `resources.py:1031-1036`, `1091-1097` | Confirmed: 409 on version mismatch. |
| Response cap covers item JSON, not the entire envelope | `resources.py:1067-1071` | Confirmed: 512,000 item bytes. |
| Existing feed preserves per-source versions/partial failures | `web/record-feed.js:1-48`, `web/unified-records.js:31-64` | Confirmed; archive/official query semantics differ. |
| Export package is already generic | `web/company-export.js:24-36` | False: validates company/Webb/HKEX view and notice. |
| Routes are generated for both delivery paths | `scripts/build_discovery.py:20-62`, `api.py:399-444`, `deploy/cloudflare/discovery.ts:27-43` | Confirmed. |
| There are 13 public family entries | Parsed `web/datasets.json` | Confirmed; families, not underlying dataset count. |
| Intended users can complete the proposed flow unaided | No observation | Unverified: usability gate. |
| Live production has headroom for more interactive reads | No current load comparison | Unverified: performance gate. |

Unverified premises: 2. New targets below are proposals, not measurements. Current
source does not establish which candidate is deployed. No production mutations made.

## 4. Information architecture

- Canonical workspace `/playground`; primary navigation label **Explore data**;
  page title **Data playground**. Keep the existing neutral directory homepage.
- `/` is discovery; `/datasets` explains scope; `/coverage` remains advanced source
  inspection; `/docs` is the developer reference; `/demo` is the neighbourhood example.
  Do not create another competing directory or silently repurpose an existing route.
- Directory actions open the workspace with stable dataset identity, language and
  a Back to results context. Preserve specialist URLs while their adapters migrate.
- An external/specialist link remains a valid fallback, but a redirect or iframe
  does not count as integration into the playground.
- Show working starter recipes with checked availability; never fabricated example
  results or an implication that every similar source works.
- API/MCP code remains under “Build with this data”, generated from the applied query.
  No account, chatbot prompt, blank canvas or forced tutorial before the first record.

```text
┌───────────────────────────────────────────────────────────────────────┐
│ mcp.hk   Explore data    Connect your AI    API docs           EN / 中 │
├──────────────────┬────────────────────────────────────────────────────┤
│ Find datasets    │ Title, plain description, source and period        │
│ [Search topics]  │ Necessary source/table/period choices               │
│ Subjects/results │ Filters [Add]  [Apply] [Reset]                      │
│ Selected dataset │ Table | Chart / Map / History (when supported)     │
│                  │ Scope + results; inspect a row                     │
│                  │ Previous / Next        Share       Download        │
│                  │ Sources ▸              Build with this data ▸      │
└──────────────────┴────────────────────────────────────────────────────┘
```

Mobile: dataset chooser, stacked controls, bounded horizontal table scroll and a
labelled detail panel with focus return. Reuse existing type, colour, language and
navigation conventions. Use a native HTML table with ordinary controls, not a new
editable spreadsheet grid. Charts/maps require an accessible table alternative.

## 5. Jobs that must work end to end

| Job | Interaction | Required meaning |
|---|---|---|
| Explore holidays | Find dataset, open event rows, choose period if needed | Readable dates/names; source period retained. |
| Inspect district statistics | Select table, filter district, choose measure, plot loaded rows | Units and period; no whole-city total inferred from a page. |
| Find a company | Name/identifier → entity → history | Exact identities, dated observations; no implied current legal status. |
| Check arrivals | Operator → route/line → stop/station → request | Provider timestamp, scheduled/predicted flags and expiry. |
| Share disclosures | Stock code → resolve issuer → inspect/share | Reused stock code does not join different issuers. |
| Open a document/blocked source | Text pages or real availability reason | Original source and next action; no fake structured preview. |

These are qualification tasks, not claims that each live provider is currently ready.

## 6. Capability contract and complete family coverage

Use a small explicit adapter registry, no new plugin runtime or service. Begin with
the generic resource adapter and one connected adapter; their actual contracts should
drive extraction. Avoid a framework of speculative callbacks for every possible API.

```text
describe(identity) → metadata, source variants, necessary choices, capabilities
inspect(selection) → typed fields, remaining choices, provenance
read(appliedQuery, adapterOwnedContinuation, signal) → result
detail(sourceQualifiedKey, sourceVersion, signal) → record/history
export(capturedResult, selection) → authorized bounded artifact

result retains:
  rows | entity | document
  scope: selectedSource | loadedPage | partialSources
  total: exact source count | unknown
  per-source versions, adapter-owned continuation
  provenance, observation/period/check dates, warnings, coverage, notices
```

Preserve source envelopes rather than flattening them into bare rows. Capabilities
are verified against APIs and current availability. Do not infer current activation
from a static catalogue badge. Source values retain original language; curated display
labels are bilingual with original keys accessible in details.

| Public family entry | Workspace mode / reuse | Completion invariant |
|---|---|---|
| catalogue | Generic resource adapter | Safe automatic preview or labelled choices/blocked state. |
| transport | Resource adapter + transport choices | Provider codes underneath human-readable reference data. |
| addresses | Address lookup | Existing exact address/location service. |
| restaurants | Place lookup + records | Existing licensed-premises query and licensing scope. |
| population | District statistics + table/chart | Period/measure; district count is not a radius count. |
| company_registry | Company/entity | Official dated observations; no inferred current status. |
| enigma | Same company workspace, archive source | Archive identity, notice and date precision. |
| hkex_daily | Disclosure | Summary scope, accepted version and source hold. |
| webb_sdi | Same disclosure workspace, archive source | Issuer resolution, amendments and numeric precision. |
| sfc_archive | Licence/entity | Archive independent of separate official activation. |
| racing | Meeting/race/profile | Reuse racing semantics/exports and explicit family gaps. |
| platehk | Plate lookup/comparison | Auction history and cohort method, not current valuation. |
| seehouse | Property/location | Transaction/building identity and available source coverage. |

Track integration and current data availability separately. A blocked family can
have a correctly integrated explanation; it cannot count as successful data access.
Merge only on exact shared source identity, never a name or stock code. Retain source
variants and conflicts in details.

### Choosing the right resource

1. Honor an explicit shared resource; never replace it silently.
2. Otherwise use a curated checked recipe matching the requested language/period.
3. Otherwise auto-open only an unambiguous readable candidate. Inspecting the first
   page of resource metadata cannot prove no other candidates exist later.
4. Where choices matter, show language, period, table or geography before format.
   Do not automatically union overlapping files or mixed reference periods.
5. Sheet/layer/path controls use returned choices. Keep opaque source labels as a
   fallback and explain them; do not fabricate friendly semantic labels.
6. Pending/restricted/unsupported/document-only are distinct. Offer a deliberate
   source read where allowed; never probe all resources looking for one that works.

## 7. Query interaction and numerical correctness

Maintain draft and applied query separately. Editing does not fetch records. Apply
validates and commits the query; table, chart, export and code examples all refer to
the applied state. Display “Changes not applied” when necessary.

- Generic v1: at most ten conjunctive equality predicates. Reject duplicate fields
  rather than overwriting them. Domain adapters can expose operations their servers
  already support. Generic contains/range/global sort controls remain absent.
- Keep strings such as `00005`, booleans, empty strings and null distinct. Missing
  is not null; no generic missing-value predicate in v1. Existing missingCount cannot
  be relabelled a null-only statistic.
- Suggestions from loaded records say “from this page”; they are not an exhaustive
  value list. Do not launch a distinct-values scan for every column.
- Resource/table/layer/source-parameter changes clear incompatible filters, selection,
  continuations and derived views. A projection change uses the displayed version
  where supported and does not silently refresh the whole dataset.

**Numeric fidelity is a first-release prerequisite.** The API schema calls ints and
floats number, but query equality checks exact types; JavaScript cannot represent all
integers exactly. Rounding, guessing type or changing legacy equality is unacceptable.

Proposed additive contract on the existing resource service, with HTTP/MCP parity:

1. Expose exact numeric kinds for scalar query fields alongside existing types metadata.
2. Accept optional typed equality predicates: field, scalar kind and textual value.
   Validate/parse server-side; reject non-finite/oversized inputs; forbid mixing with
   legacy filters. Reuse existing exact matching and filter-count limits.
3. Offer an opt-in browser presentation sidecar containing exact server-formatted scalar
   values aligned to projected rows/columns. Row details and JSON evidence export use
   exact serialized server values, not a JS Number round trip. Default clients retain
   the current envelope. Include added bytes in a measured whole-response budget.
4. Use one codec across filtering/display/export; no second query engine. State source
   reader precision limits: formatting cannot restore digits already lost upstream.

T1 must prove this small backward-compatible shape against mixed numeric fixtures.
Finalize field names and byte budget from that probe before building numeric controls.
If it cannot remain small and correct, stop that path for design correction; do not
ship plausible incorrect numbers. String/bool/null exploration can proceed independently.

## 8. Views, scope and useful limits

**Table:** start with readable scalar columns, 20 rows per page (proposed UI default,
also the existing API default). Use Previous/Next and bounded page history, not infinite
accumulation. Inspect nested values on demand; do not dump large geometry into cells.
Show exact source count only where returned; preserve unknown totals. No global sort
arrows for page-local ordering.

**First chart:** simple local SVG bar/line plus an accessible data table, without a
general chart-builder dependency. Require verified field meaning/units or an explicit
user mapping; column names that look like amounts/dates are insufficient. The chart
covers this loaded page, labelled beside the plot and in exports. A bar represents a
record; do not silently aggregate duplicate categories, currencies or mixed periods.
A line additionally requires known time ordering and valid continuity; never bridge
unknown gaps. Changing pages replaces the chart and its scope. No extra data fetch.

**Map:** follow a proven spatial resource, with known CRS/axis order and finite valid
coordinates. Do not read HK1980 metres as WGS84 lat/lon. First vertical slice does not
depend on external tiles, geocoding or CSP changes. Existing place experiences remain
usable. Geometry failures remain visible in table/details.

**Entity/history:** keep history/relationships as a domain view inside the shared
shell. A graph needs established identity and edge semantics; raw schema inference
cannot establish them. Do not make table flattening a requirement for integration.

## 9. State, sharing and reproducibility

```text
idle → finding → selecting → inspecting → needsChoice → reading → ready
                                           ↘ blocked / failed
ready → draft edits → Apply → reading → ready | empty | partial | failed
ready → Next (same versions) → reading → ready | versionChanged
ready → Share / Download (capture applied result, never draft)
```

Use a request generation and AbortController per logical flow. Obsolete search,
schema, detail and export completions cannot alter a later dataset/query. A failed
refresh may retain a labelled previous result; it cannot become newly observed data.
Switching queries invalidates pending download completion.

Two kinds of state:

- Share recipe: schema version, stable dataset/resource identity, selectors, applied
  typed filters, columns, supported view configuration and language. Encode validated
  bounded state in the URL fragment; proposed encoded ceiling 8 KiB. No records,
  credentials, cursor tokens or receipts. Reject excess size without a new short-link
  backend. Invalid/unsupported state opens an editable error view.
- Local session: displayed version vector, adapter-owned continuation, bounded page
  history, selected row and focus. Share query intent, not these transient tokens.

Copy link says “Shares this query; results may change.” Reopening starts at the first
page and restores supported inputs. Do not silently replace missing resources/fields
or promise historical pages. Existing legacy checkpoint URLs remain supported.
Live arrivals restore a current lookup; historical version pins are only offered
where the actual adapter supports them.

A downloaded evidence package is the captured result. A recipe link is not an immutable
snapshot. Fragments reduce incidental logging, not access control or confidentiality.
Preserve existing consent and pathname-only analytics. Never log query text, addresses,
record identifiers, source URLs or share state as event properties.

## 10. Sources, failures and export policy

Show reference period, observation date and source-check date separately. “Checked
today” cannot make historical facts current. Small source/date context stays by the
result; detailed provenance/technical diagnostics go in disclosures.

| Failure/state | User sees | Recovery / invariant |
|---|---|---|
| Required sheet/layer/path/parameters | Labelled choices | No query until valid. |
| No matches | No matches in selected source + applied filters | Reset; preserve coverage meaning. |
| Version changed (409) | Source changed; restart to use new version | No mixed-version append. |
| Partial independent sources | Available results + named missing sources | Retry failed sources only; no invented exact total/completeness. |
| Ordinary stored refresh failure | Previous accepted data visibly marked | Preserve retrieval/observation dates. |
| Arrival TTL expires | Expired; refresh for arrivals | Remove from active results/export, retain timestamp/status; no stale live fallback. |
| Saved field disappeared | Explain missing field; retain editable recipe | No silent broadening. |
| Rate limited/busy | Plain message and Retry-After countdown | No request/provider retry storm. |
| Cold recovery | Existing bounded recovery progress | Reuse existing attempts; allow cancel. |
| Huge response | Choose fewer columns/narrower data | No silent truncation. |
| Restricted/unsupported/document | Real capability + original source | No arbitrary user-URL fetch proxy. |
| Invalid shared state/source HTML | Safe error/text | No reflected HTML or executable payload. |
| Export notice/capability absent | Export disabled with reason | Read access does not establish redistribution permission. |

Downloads say **Download this page · N records** or the exact source-supported
selection. CSV is convenient; an evidence package includes exact JSON, safe CSV,
schema, applied query, source notices and checksummed manifest. No all-pages crawl.
Source terms, current restrictions, exact versions and selected scope travel with it.

Extract only tested pure `csvCell`, `sha256`, `zipStore` helpers into a small export
module. Existing pagePackage keeps its company/Webb/HKEX policy checks; the new
generic exporter supplies its own verified source notices/terms. Two callers justify
the extraction: existing pagePackage and proposed playground export. Expected benefit
is shared correctness; net line savings are unknown and not a reason for broader cleanup.
Keep formula escaping/leading zeros, capture applied state before hashing, hash actual
Unicode bytes, revoke object URLs. Do not claim browser-rounded JSON is lossless.

No public writes, new auth, arbitrary SQL, source HTML injection or code execution.
Preserve safe link schemes, CSP, source-network guards and independent activation gates.

## 11. Architecture, performance and implementation footprint

```text
directory / deep link / checked recipe
                ↓
generated bilingual static shell (Worker + Python)
                ↓
applied state → adapter → existing read-only HTTP service
                ↓                 ↓
typed presentation ← versions / provenance / capabilities
                ↓
table / chart / detail → share recipe or captured export
```

Proposed authored modules: playground HTML/CSS/controller, state/recipe module,
adapter module, views module and a small pure export module. Reuse http.js, MhkI18n,
shared CSS and RecordFeed. Split domain adapters when actual size demands it; no new
framework, plugin host, storage system or BFF. Server work is additive typed presentation
and bounded scan admission in the existing resource service, with MCP parity.

Integrate discovery metadata/rendering, translations, generated assets, route lists,
filtered-page policy, canonical metadata and no-JS fallback. Generated outputs are
rebuilt, not hand edited. The Worker and Python routes must agree.

| Area | Proposed budget/behavior | Verification |
|---|---|---|
| Idle shell | No all-family status/coverage fan-out | Network trace. |
| Unambiguous warm dataset open | Metadata selection + one schema + one first-page query | Count actual calls, no recursive resource probing. |
| Draft filters | Zero record calls before Apply | UI network assertion. |
| Generic query | Existing max 100 rows; UI default 20; retain source caps | API/reader tests. |
| Client retention | Current plus at most two recent pages | Proposed cap; wide/nested memory measurement. |
| Scan admission | Bounded active scans, specific busy response + Retry-After | Concurrency test and measured maintenance headroom. |
| Cancellation | UI ignores obsolete results; server releases only on real completion | Abort does not promise to stop an active to_thread job. |
| Live feeds | Explicit refresh, no background polling | TTL/quota tests. |
| Charts | Current page only; no extra reads | Point-to-record and scope assertions. |
| Export | Existing 16 MiB ZIP payload ceiling; only displayed bounded data | Actual byte and scope checks, never fetch more to fill budget. |

Existing load semaphore does not prove admission around query scans. Add bounded
in-process scan admission and cooperative monotonic deadline checks. Do not release
capacity or close a FileRows reader while its worker thread still uses it, including
after cancellation. Choose scan concurrency/deadline and whole-response cap from
measurements; no new queue or automatic quota/capacity increase.

Measure baseline/candidate interleaved on the same runtime with warm/cold tabular,
file-backed and nested/wide data. Record engine, dataset size, N, median/p95, bytes,
request counts and maintenance overlap. Provider latency is separate from render time.
Proposed UX targets: local feedback within 100 ms, controls usable while waiting,
zero record reads on typing. First useful result within 30 seconds is a usability
target, not a measured SLO. No performance improvement claimed in this plan.

## 12. Work sequence and review boundaries

Use a clean checkout of then-current main, preserving dirty work. Keep provider fixes
separate. Implement sequentially: shared state, codecs, adapters and route generation
are tightly coupled; extra agents/worktrees add little independent progress here.

| Task | Deliverable | Depends on | Done / stop criterion |
|---|---|---|---|
| T1 | Fixtures + additive codec/presentation proof | — | Mixed kinds/unsafe numbers; legacy HTTP/MCP parity; settle names and byte cap before numeric UI. |
| T2 | Static shell, routing, bilingual navigation and state | T1 contract | Worker/Python parity, no-JS fallback, restored language; no eager data fan-out. |
| T3 | Generic adapter and human source choices | T1–T2 | Tabular/calendar/workbook/nested fixtures; real blocked/document state. |
| T4 | Visual equality filters, columns, detail and paging | T3 | Draft/apply, version drift, typed values and obsolete-response tests. |
| T5 | Page chart, share and exact bounded export | T4 | Honest scope, restored recipes, correct notice, exact evidence bytes. |
| T6 | First connected adapter: company/entity | T2–T5 | Archive/official sources, independent versions, partial failure and history. |
| T7 | Remaining family checklist | T6 proven contract | Every family has a real mode or explicit blocked capability, no redirect counted as integration. |
| T8 | Qualification and release | Candidate scope ready | Required checks, headless QA, comparative load evidence and documented production process. |

Release A: T1–T6 as one complete reviewable preview: generic resources, a chart,
entity workflow, sharing and export. Label supported families precisely.

Release B: T7–T8 qualify family-wide coverage. Prefer one integration PR while review
size remains manageable; any further split is a complete useful family group with its
own checks and deployment receipt. Base estimate: two feature releases, not a promised
time schedule. Further PRs add CI, review, route consistency and rollout verification.

Block Release A on broken precision, versioning, truthful source states, export or core
interaction. Block family-wide claims on incomplete integrations. Load regression blocks
rollout; it does not authorize more production spending or higher shared quotas.

### Explicit later work

- Natural-language assistance: first examine real failed tasks; reuse visible query model.
- Generic contains/range/global sort, full aggregates/export: require measured server support.
- External basemaps, automatic CRS conversion, relationship graphs, arbitrary joins:
  require spatial/identity/period semantics and independent review.
- Accounts, saved workbooks, uploads, short-link storage and dashboards: unnecessary for
  the first public exploration loop.
- New ingestion/providers/rights and fresh SFC activation: separate gates; show their real state.

## 13. Verification and release evidence

Reuse receipts: **17 existing tests passed** across catalogue-ui.test.mjs,
record-feed.test.mjs and company-export.test.mjs on this baseline. A bounded ResourceQuery
probe confirmed distinct integer/float/string/bool/null parsing. These do not test the
unimplemented feature. No new acceptance suite was built during planning.

| Layer | Required meaningful regressions |
|---|---|
| Codec/API | int/float/integral float, negative zero, big int, precise source string, bool/null/absent/empty, dotted keys; legacy behavior; whole-response cap. |
| Admission | Slow concurrent scans, busy/deadline, cancellation, actual completion before cleanup; event-loop and maintenance responsiveness. |
| State | Versioned recipe, malformed/oversized/forged values, vanished field/resource, back/forward/language, no shared cursor. |
| UI | Required choices, draft edits without fetch, Apply/reset/projection/page/409, late query/detail/export rejected. |
| Views | Source text safely rendered; exact numbers; scoped chart/units/gaps; unknown count retained. |
| Domains | Company partial failure, reused issuer code, inactive SFC, racing gaps, plate cohorts, property identities and live TTL. |
| Export | Independent ZIP/CSV reader, actual Unicode hashes, notice/terms, formula text, leading zeros, exact JSON and captured versions. |
| Delivery | Generated EN/Traditional Chinese, Worker/Python parity, metadata/canonical policy, legacy links and API docs. |
| Accessibility | Keyboard flow, focus return, table headers, loading/errors, zoom/narrow viewport/reduced motion, chart alternative. |
| Privacy | Existing consent; no fragment/query values, addresses or IDs in analytics. |

Use existing Node/Python runners for deterministic contracts and headless Playwright
for real DOM, layout, downloads, clipboard fallback and language flows. DOM stubs do
not establish focus, viewport or serialization correctness. No visible browser windows
needed for routine QA. Keep existing feed/export/legacy-route regressions.

Candidate checks: `bash scripts/check.sh all` in the locked environment with
`PYTHONPATH=src`, plus required CI Python versions. Add tests for changed behavior,
not an arbitrary test count.

Follow docs/production.md for exact candidate/CI receipts, controller/container
maintenance precautions when server code changes, actual adoption, live HTTP/MCP
regressions and fresh-backup isolated restore where required. Restore configured
schedules, retain failures and verify code/assets agree. Rollback matching code/assets;
optional additive contracts preserve old clients. Never roll back source facts to hide
a UI failure. Source/CI, deployed code, live checks and human usability are separate.

Usability pilot: five intended nontechnical users perform find/filter/share in their
preferred language. Proposed gate: four finish unaided; all can identify source and
whether the result is current/historical. Record task failures/duration and small-sample
limitations; do not call this representative conversion evidence. Human usability is
unvalidated until real people complete those tasks; deployed software alone is not proof.

## 14. Consolidated review and decision record

These are proposed plan revisions under the user's request to think and plan deeper,
not approvals of implementation, deployment, production access or spending. Routine
structure choices are resolved here; uncertain facts are explicit validation gates.

| Finding | Severity / confidence | Planned resolution |
|---|---|---|
| F1 Table-only model fails several jobs | High / high, inventory/UI | Capability modes and full family checklist. |
| F2 Numeric schema/JS/backend mismatch | High / high, source/probe | Typed presentation proof; legacy equality unchanged. |
| F3 Repeated scans/cancellation | High / high, query source | Apply + bounded admission/deadline + completion cleanup. |
| F4 Export helper is policy-specific | High / high, source/tests | Pure-helper reuse; adapter export authorization. |
| F5 Share is not immutable evidence | Medium / high, pagination contracts | Recipe link versus captured evidence package. |
| F6 Worker/self-host route drift | Medium / high, build source | Generated bilingual parity/metadata tests. |
| F7 Charts can imply coverage/meaning | Medium / high, query/source schema | Loaded-page scope, units and semantic gates. |
| F8 New paths lack current test coverage | High / high, test inspection | Explicit layered regression and real-user gate. |

Architecture: F1/F2/F5/F6. Code quality: F4. Tests: F8. Performance: F3/F7.
No revised failure path is intentionally left silent without a planned handler/test;
handlers and tests remain unimplemented. This is not a clean code audit.

REALITY: premise-table pass Source-backed premises and unverified=2 recorded at docs/designs/mcp-hk-data-playground-plan.md:43-62.
REALITY: already-done pass Fetched main=8504d79; checked history has directory/docs work, no playground implementation.
REALITY: surface-check pass resource_api.py:24-118 verifies existing routes/limits; new route/contracts are labelled proposed.
REALITY: binding-decisions pass User scope and proposed status preserved at docs/designs/mcp-hk-data-playground-plan.md:8-29; no user-selected architecture overwritten.
REALITY: numbers pass Inventory 13 measured by parsing web/datasets.json:1; tests 17 measured and recorded at docs/designs/mcp-hk-data-playground-plan.md:403-407; new targets are proposed at docs/designs/mcp-hk-data-playground-plan.md:334-360.
REALITY: deferred-asks pass Family-wide interaction remains Release B; deferred work recorded at docs/designs/mcp-hk-data-playground-plan.md:379-399.
REALITY: pr-count pass Proposed release boundaries and added split cost recorded at docs/designs/mcp-hk-data-playground-plan.md:379-386.
REALITY: units n/a No input-unit change; chart measures/dates retain source semantics (section 8).
REALITY: perf-table finding Comparative live/headroom measurements remain unperformed; release gate section 11.
REALITY: recall n/a No catalogue matching/index change; source selection/partial outcomes preserved (sections 4/6).

Primary technical guidance: [MDN JavaScript Number precision](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Number)
and [W3C native table guidance](https://www.w3.org/WAI/ARIA/apg/patterns/table/).
External guidance does not establish dataset meaning or production readiness.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---|---|---|
| Product scope | User: Think harder and Plan deeper | Universal interaction model | 1 | Proposed revisions saved | F1/F5/F7; preview/family-wide distinction. |
| Engineering plan | plan-eng-review workflow | Architecture, code, tests, performance | 1 | Plan saved; registry not persisted | Eight findings mapped to implementation/verification. |
| Outside Review | Claude Code plan-review invocation | Independent plan challenge | 1 | Unavailable: authentication | No model review completed; no independent coverage claimed. |
| Usability | Nontechnical task pilot | Validate human outcome | 0 | Not run | Audience/task success remains unverified. |

**OUTSIDE COVERAGE:** Claude Code plan review could not authenticate. The required native fallback capabilities are not available in this session; no fallback dispatched. Native engineering analysis is complete; independent review coverage is missing.
**VERDICT:** Deeper plan prepared; codec/admission proof and candidate checks still required. No feature/deployment completion claimed. Formal review registry was not persisted outside the workspace.
**UNRESOLVED DECISIONS:**
- Codec field names/whole-response budget require T1 compatibility proof; scan concurrency/deadline require comparative measurements. Product direction remains proposed.
