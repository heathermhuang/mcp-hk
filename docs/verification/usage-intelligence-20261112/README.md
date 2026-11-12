# Usage intelligence implementation verification

This is source/local-runtime qualification, not a production release receipt.
The isolated feature branch starts from main `8e4e037a237e768240ac448902b2f1361f7b1edb`.

## Implemented

- A separate SQLite-backed analytics Durable Object with bounded observation,
  event, identity, dimension, keyword and storage budgets. Legacy quota storage
  and the authenticated legacy report remain separate.
- HTTP/MCP operation coverage, sanitised catalogue demand, reported/inferred client
  families, daily network estimates, known/unknown returned counts, source versions,
  stale warnings, outcomes and observed-duration histogram bounds.
- First-party refusal migration before data scripts, opt-out propagation through
  credential stripping, and CORS support for the explicit opt-out header.
- Space-Saving keyword estimates, explicit uncertainty and coverage reporting,
  completed-week windows and a standard-library-only private HTML/JSON report CLI.
- Existing-tick daily digest generation, private closed-day R2 aggregate archives,
  SHA-256 read-back verification and three archive attempts per reporting day.

## Checks

- Required check groups passed: formatting/lint, 1,183 Python tests passed and 122
  existing optional/live/PostgreSQL-dependent tests skipped; Worker type generation,
  typecheck and all 200 Worker tests passed with Node 22.23.4. This includes the
  final midnight and UTF-8 size regressions. The pre-push hook reruns the required
  entrypoint against the exact committed tree.
- Actual workerd/Miniflare runtime coverage includes private-report authentication,
  the real edge/controller admission and streaming observation methods (with only
  the backend transport replaced by a deterministic fixture), opt-out exclusion,
  credential stripping, durable counting, duplicate observations, scheduled digests,
  R2 read-back checksums, and independent SQLite restore/integrity verification.
- A bounded 500-observation local SQLite/extractor probe recorded all observations:
  p50 0.192 ms, p95 0.403 ms. This is not a production network/controller latency
  result, throughput guarantee, or provider outcome.
- The CLI's private offline HTML output is tested for content escaping, no active
  external resources, restrictive CSP and mode 0600. No production stats or
  credentials were included in test artifacts.
- The unchanged homepage Chromium suite passes all 11 cases after using ordered
  deferred loading for the privacy script. A new browser regression deliberately
  delays that script and proves stored refusals and browser GPC reach the request
  header/cookie before catalogue queries. Production-host requests are intercepted
  locally and no production analytics are sent. The existing homepage assertions
  and timeouts were preserved; the fix removes parser blocking in source HTML.

The integration test declares its direct development dependencies. Its pinned
workerd binary supports the existing production compatibility date; the production
Wrangler version and compatibility date are unchanged. Both production/local
required checks use Node 22; Node 24 is not the documented project toolchain.

## Remaining before live completion

- No merge/deployment, controller/container adoption, ordinary production digest
  receipt, live public-data backup restore or real customer-use claim is included.
  Follow the resource-cron pause/adoption/restore procedure in `docs/production.md`.
- Normal operator credential access is required for live verification. This
  implementation does not depend on repairing the separate GA connection.
- A notification destination has not been selected. Digests explicitly show
  `notification.status=not_configured`; generation is not notification delivery.
  Reports are private operator exports; there is no new hosted admin login.
- Network clients are estimates, not people. Keyword ranking is approximate and
  bounded; unknown metadata and collection-budget losses stay visible. Optional
  installation/workflow correlation and backend cache/upstream enrichment remain
  outside this first implementation.
