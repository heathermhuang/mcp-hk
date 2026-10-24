# Audit-to-candidate security delta review

Audit `4692f9a4c199aaabc75e26eb837cbb918e672553`; freshly fetched implementation base
`1b9c71e6e73945134d92c876146e653568b7202c`. Exact final SHA and the complete binary-safe
diff are in the external frozen bundle. This is a scoped source review and local
verification record, not an independent full security audit or assessor closure.

## Post-audit baseline additions

The audit-to-base delta spans 70 files (8,579 insertions, 23 deletions). Reviewed
security-relevant entry points and contracts:

- `api.py`, `company_api.py`, `companies.py`, `services.py`, `tools.py`, `contracts.py`,
  `connected.py`, `sources.py`: new company HTTP/MCP routes reuse typed read contracts;
  backend origin/token are operator configuration, not request-selected destinations.
  HTTPX environment distrust and source/output bounds already existed on that adapter;
  this candidate adds operation/edge accounting to it. Other review endpoints retain
  their existing credential boundary. No anonymous write/restore endpoint is added.
- `deploy/cloudflare/company-downloads.ts`, Worker routing and export UI: R2 object
  paths are constrained by version/hash/file patterns; manifests, archive parts and
  content hashes are checked; downloads stream and have a two-download semaphore.
  Publication is an authenticated operator action under the maintenance lease and
  requires expected pointer hashes. Downloads consume existing admission but fetch
  no upstream source. Publication is not transactional across two R2 pointers; a
  failed/unknown response still requires the existing reconciliation procedure.
- `curated/backend.py`, `read.py`, `security.py`, configuration and container env:
  dedicated reader authorization and restricted DB role, parameterized reads, signed
  cursors, output/query/concurrency bounds and source qualification are present.
  Review included the reader role rejection and source-export isolation contracts.
  PostgreSQL/MariaDB integration tests requiring separate servers remain skipped in
  the ordinary suite; no production database or credential was accessed here.
- Archive acquisition/extract/SQL/restore/qualify modules and curated build/normalize/
  export/backup are operator/offline tooling, not public upload handlers. Reviewed
  their command separation, fixed-table projections, source pin/isolation checks,
  refusal to execute source SQL as an unchecked import and bounded subprocess/file
  contracts. Their full adversarial database/archive coverage was not re-audited.
- `web/companies.js`, company export/fields, translations/discovery: publisher values
  are rendered with textContent; same-origin download paths are constrained. New
  discovery entries do not assert source currency. UI/client functional tests are
  reused from the required gate; this is not a complete browser security audit.
- Lockfile additions (including PostgreSQL client dependencies), curated workflow/
  Compose/Caddy configuration and docs were reviewed as new deployment surface.
  There is no evidence here of their current deployed configuration or reader grants.

The original auth, parser and usage mechanisms were unchanged at the implementation
base. The original report's corrections remain: anonymous read access is intentional,
HKMA already has an aggregate 8 MB post-page check, and forwarding a method alone
never established backend acceptance.

## Candidate changes and review conclusions

1. Auth rotation/containment use the production storage `transactionSync`, with no
   async work between validating durable state and committing the replacement. New
   key/session digests are computed first; owner/session/registration state is checked
   again after crypto. Original owner expiry is preserved. Legacy cookies fail closed;
   recovery upgrades owners. Tests cover rollback on a failed audit write and pending
   claims/issued tokens being destroyed by scoped containment. Auth/data storage stay
   separate; fork publishing and optional public access are retained.
2. Record ZIP members are inspected by content before deeper record parsing. Shared
   counters include actual workbook reader decompression (including repeated reads),
   not only ZIP central-directory sizes. Normalized rows/provenance have incremental
   caps before archive serialization/reparse. Positive workbook tests retain formulas
   and leading-zero strings. Before receipts demonstrate late recursive work and a
   9,099,000-byte normalized result accepted by the audit parser.
3. Edge allocation and adapter budgets share one grant per operation. The controller
   dispatch helper is tested with a spy backend; denied admission causes zero dispatch
   and zero source effects. Internal headers are stripped at both public/authenticated
   forwarding boundaries; curated credentials are injected only for their configured
   target. Unknown results retain reservations. Failed source attempts and decoded
   chunks are recorded separately from application-response bytes. API and stdio tool
   paths receive request budgets. Maintenance/bootstrap have explicit separate scopes.
4. **Blocking finding for this candidate:** local Docker direct egress still bypasses
   the declared platform policy. HTTP 80/23456 and raw TCP 23456 reach an owned sentinel,
   despite a deny-all fallback and fresh start. Gate #2/#6 remains failed. No claim is
   made that the gateway prevents all container egress. Isolated Cloudflare staging
   and a vendor-supported resolution/qualified topology are required before release.
5. The pinned SDK supports GET SSE and POST; stateless DELETE cannot terminate a
   session. Both edge and backend reject unsupported methods, preserve OPTIONS and
   leave protocol negotiation to the SDK. HTTPX/urllib clients explicitly distrust
   environment proxies and ambient CA paths; self-host resource downloads retain
   validated dial targets and TLS hostname checks. The Worker uses strictly-public
   fetch with no VPC binding. It does not offer application-owned all-answer IP pinning;
   hosted network equivalence and valid SSE clients remain staging/retest gates.
6. Tool instructions and an envelope trust marker identify source content as data;
   source strings and provenance remain intact. This is contract hardening, not a
   downstream model injection guarantee. Locked installation, loopback guidance,
   SQLite ATTACH/native-extension denial and bounded operator body reads are scoped
   hardening. No exploit/CVSS classification is invented for H1–H6 or IDs 3/5/7.

## Residual coverage and disposition

See the [status matrix](README.md). In addition to the blocking egress test, outstanding
work includes hosted DNS/rebinding/private-address controls, representative HKMA/
ArcGIS/curated upstream controls, approved daily cost settings, named model/client
injection qualification, remote staging, the exact assessor addendum and actual
assessor retest. Ordinary full-suite skips and development-only transitive npm
advisories are recorded in receipts; updating to current Wrangler did not eliminate
all tooling advisories. Do not apply npm's suggested downgrade/force fix blindly.
No production probe, auth bulk mutation, paid provisioning, publishing, assessor
message, merge or deployment was performed.
