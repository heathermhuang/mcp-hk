# Review of the mcp.hk UX completion plan

Date: 25 October 2026. Reviewed document: [mcp.hk UX completion plan](ux-completion-2026-10-25.md).

Result: **no blocking findings in the revised plan**. It is ready to guide implementation. This was a structured self-review across product, design, engineering and developer experience, followed by revisions; it was not an independent-user usability test or an implementation review.

## Review scope

The review checked the 16-page audit against the work packages, repository ownership, dependency order, data semantics, failure states, URL compatibility, performance, verification and release requirements. The current main commit and file inventory were read from GitHub; representative logic came from the live assets captured during the audit and the separate inspected security checkout. The plan explicitly requires reconciling the eventual implementation checkout with the live deployment before code changes.

## Findings resolved in the plan

| Priority | Finding | Correction incorporated | Acceptance evidence required later |
|---|---|---|---|
| P1 | A nicer oversized-response error could satisfy the original weather acceptance while the promoted task still failed. | Require a functioning default weather preview from a verified existing source. Keep safe recovery on the oversized source, and treat absent usable preview as incomplete work rather than success. | A04 and a real weather browse-to-record receipt. |
| P1 | Browser-only grouping of a page of matching company name facts would leave duplicates across pages and produce misleading company counts. | Specify an opt-in grouped contract in the curated read service and typed gateway, with source/version/entity grouping and query-bound signed cursors. Leave omitted grouping backward compatible. | A06 plus PostgreSQL contracts covering aliases across page boundaries. |
| P1 | One company search could be misread as permission to merge official BRNs, money-lender identities and Webb archive IDs. | Separate source groups and identities, pin versions and preserve leading zeros. No name-based linkage or current-status inference. | Same-name/different-identity fixtures, A06–A08. |
| P1 | Returning/exporting all matching aliases for each grouped company could create an unbounded payload. | Limit grouped pages and displayed alias samples; keep further facts behind version-pinned pages. Export exactly the labelled summary/evidence scope, preserving existing fact exports. | Response-bound tests and export count/provenance checks. |
| P1 | The two current company UI modules mutate URL/state differently; a visual consolidation alone would retain competing controllers. | Assign one controller for the shared search and URL with separate per-source request/cursor/version state. Preserve the old archive and official deep links explicitly. | Back/Forward, old bookmarks, cancellation and partial-failure browser tests. |
| P1 | The browser/gateway might deploy before grouped-query support on the separate curated service. | Identify `curated/read.py`, `curated/official_read.py`, `curated/backend.py` and `deploy/curated/`; require backend capability/adoption before enabling the new consumer. Define additive migrations and compatible rollback. | Backend/gateway mixed-version contract tests and actual service adoption. |
| P2 | Shareable property searches could add private free-text addresses to URLs and analytics. | Share selected public building IDs and view/filter/locale state. Keep new free-text input in current-tab state and preserve existing redaction. Generic record queries are not automatically replayed. | A09 and A17, including blocked storage and refresh. |
| P2 | Preview simplification could hide raised limits, repeated retries or extra metadata refresh calls. | Preserve the byte/time/request safeguards, cap automatic schema/query work and remove unconditional coverage/resource refreshes after a preview. Add a request-fan-out check. | A04, A18 and A21. |
| P2 | The API guide could finish with a documented limitation instead of a working example. | Require both introductory HTTP and generic-resource tutorials to return meaningful records; limitations and alternate sources supplement the worked success. | A13 with copy/paste request receipts. |
| P2 | A Copy result or HTTP health check could be reported as a connected AI client. | Require actual client tool discovery and a source-linked read. Unexercised client verification is explicitly pending. Verify official client documentation at implementation time. | A12 for each claimed verified client/version. |
| P2 | A map, framework migration, new contact service or account redesign would enlarge the repair without addressing its main blockers. | Defer new providers/frameworks/identity matching. Improve map-free geography and reuse only verified contact/account paths. | Scope review of each change package. |
| P2 | Accessibility/localization could be postponed until the last package, or an automated false positive could become unnecessary work. | Apply shared design/state rules from UX-01 onward; reserve UX-08 for final verification/correction. Verify actual rendered semantics before changing labels. | A15/A16 and representative keyboard/screen-reader/browser receipts. |

## Cross-functional assessment

**Product:** The plan prioritizes working search-to-result journeys, company discovery and setup. Home/navigation changes depend on working destinations. Existing coverage remains truthful; new data acquisitions and features are bounded out. The two-minute search and five-minute setup figures are proposed walkthrough targets, not claimed research results.

**Design:** The revised hierarchy puts task, input and result before diagnostics. It preserves the established wordmark, palette and OS theme behavior. It defines readable supporting text, mobile layouts, bilingual authored copy, focus behavior and recoverable page states without prescribing a broad visual rebrand.

**Engineering:** The plan names the significant backend dependency behind company grouping, source/version-bound cursors, compatibility parsing, response/query bounds, async race handling and reversible rollout. It protects the distinction between empty, failed, unavailable, old observations and expired source checks. The production runbook remains the release authority.

**Developer experience:** Connect owns the client-specific settings; guides explain complete tasks rather than duplicate settings. Swagger becomes organized reference with a shared entry shell. Real client proof and copyable HTTP success remain separate acceptance gates.

## Implementation checks still required

These are explicit execution tasks, not unresolved product choices or reasons to stop planning:

1. Identify the exact deployed source/asset/backend versions and refresh main in an isolated checkout. Reconcile any changes since the planning baseline.
2. Diagnose the rainfall payload: the observed error and inspected byte cap are evidence; the precise record-path/projection fix remains to be demonstrated.
3. Measure grouped-search query plans and confirm the production curated database/host can adopt the optional contract without new infrastructure. Include the PostgreSQL integration checks.
4. Verify official client instructions and the available installed client versions. Do not buy subscriptions, change external accounts or infer consumer-app availability to satisfy the client matrix.
5. Verify actual existing private contact/account paths before publishing their links. Their absence does not justify inventing one.
6. Recheck current production release/security constraints. The prior security note is historical context and does not establish the present release state.

## Verification of the plan artifact

The final plan contains eight sequenced work packages, explicit changes for all 16 audited pages, a file/service ownership map, 21 acceptance scenarios, bounded failure/performance checks and candidate-specific release/rollback instructions. The review corrections are incorporated in the linked plan. No application code, deployment or external account state was changed for this planning task.
