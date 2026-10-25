# Consolidated review of the three implementation plans

Reviewed 25 October 2026 by the parent planning chat, after drafting all three
source plans. This is a technical planning review against current code/runbooks
and official source documentation. It is not independent legal clearance, a code
review of unimplemented collectors, or proof of a live source pilot.

## Result

No blocking **plan defects** remain from this review. The plans are ready for
separate engineering execution. Source-access/output qualification, real pilots,
capacity/recovery qualification and actual live acceptance remain explicit gates;
the review does not resolve them by assertion. Implementation review and fixes are
required again in every execution chat after its code is complete.

Pass one checked each plan's identity, temporal semantics, scope, source rights,
collection bounds, contracts and acceptance tests against the baseline. Pass two
checked interactions across the three plans: migrations, shared adapter/config
edits, source policy changes, publication locks, aggregate capacity, backup scope,
deployment/adoption, rollback and existing company-maintenance ownership. The final
plans incorporate the following controls and corrections.

| Priority | Risk checked | Final disposition / required execution proof |
|---|---|---|
| P1 | Unqualified source reads or public modes presented as authorised because synthetic validators exist | Every source has an evidence matrix and independent mode gate; disabled network/surfaces can be implemented/tested. Requests remain unsent; no paid commitment is inferred. Actual allowed-mode evidence is needed before live pilot/activation. |
| P1 | A deployment flag or public purpose value bypasses source rights | shared.md now requires checksum-pinned reviewed policy, audited activation and rechecking at collection/publication/export, including mid-run expiry/revocation tests. |
| P1 | HKEX event-date ordering falsely proves a seven-day filing window or incremental completeness | hkex.md requires a qualified filing inventory/bounding method. Missing basis fails filing-window acceptance; any event-window subset is labelled separately. No invented late-filing horizon. |
| P1 | Three simultaneous changes overwrite configuration, schema/pointers or the controller while maintenance owns a lease | shared.md defines atomic local release claims for these chats, current-main integration, mixed-order migrations, source-scoped expected-version publication and authoritative DB/Cloudflare lease checks. Existing company-maintenance jobs remain separately owned. |
| P1 | Gateway snapshot restore is claimed as recovery of new PostgreSQL data | Every track must prove complete source-schema/capture/policy backup coverage, independent offsite download/restore and full pilot comparisons. Exact daily RPO requires a genuine ordinary occurrence. |
| P1 | Source denial/empty result/drift changes status to revoked, clears data, or publishes a partial group as complete | Each plan separates failures, unknown/empty facts and completeness. Last accepted pointer survives failure; policy-denied output can still be withheld. Real and synthetic failure tests verify both distinctions. |
| P2 | Racing sample accepted as all-runner/season/history/vendor parity | hkjc.md separately reconciles meeting, declared runners, season inventory and each source family/range; withdrawals omitted by results need another qualified source. P10 has a measured prospective start/cadence and cannot recreate historic odds. |
| P2 | Fresh SFC data inherits historical archive IDs, purpose or currentness | sfc.md uses exact corporate CE and regime/type, a tracked cohort of at most 25, independent observation/effective dates, no name-only joins or contact/person-role expansion, and separate archive presentation. |
| P2 | HKEX amended/withdrawn/deemed interests are silently counted as present ownership or executed trades | hkex.md preserves serial chains, unresolved links and source sections; detects cycles and states; typed positions stay separate and no inferred aggregate ownership is published. |
| P2 | Three independently reasonable collectors exceed one host's budget or need paid growth | shared.md imposes proposed per-source caps, one combined allocation/WAL/backup/restore sheet, initial growth reservations and no unreviewed resource increase. Limits are not provider-granted quotas. |
| P2 | Public cursors outlive a permitted source-retention window | shared.md requires explicit cursor expiry compatible with the source's retention; unknown history/export permissions keep modes disabled. |
| P2 | A HEAD request, fixture screenshot or code flag is counted as live product acceptance | Each plan requires real HTTP/MCP version/value parity, EN/繁中 browser journeys, actual allowed archive content checks, backend/DO adoption and ordinary operation receipts. |

## Execution readiness and handoff checks

- Verified mcp-hk remote main: `9521ef6857e92250d35b45dca09337eb328ed3d2`.
  Execution chats must fetch current main and preserve later accepted work.
- Inspected existing curated schema, backend/API/tool route inventory, production
  runbook and current permission-brief/synthetic-contract boundaries. Proposed
  modules/migration numbers/API names must still be reconciled with current main.
- Each source plan contains ordered dependent work packages, typed schema/identity
  contracts, bounded pilot and incremental rules, REST/MCP/browser ownership,
  source-specific test matrix, release/rollback and durable done evidence.
- Shared ownership covers dirty-work preservation, isolated clones/test databases,
  minimal shared edits, current-main integration, mandatory exact-HEAD checks and
  CI, source flags/policy, production serialization, aggregate budgets and recovery.
- Parent planning documents contain no credentials or private capture payloads.
  Relative plan links and work-package/acceptance structure are checked by a local
  bounded script. Application tests are for the implementation chats; this turn
  does not claim new source software was tested or released.

## Remaining external decisions and observation gates

| Track | Gate that must be established before claiming live source acceptance |
|---|---|
| HKJC | Exact authorised results/profile/history/observation routes and independent output rights; real complete meeting/season; measured history/series limits |
| SFC | Qualified licence-verification purpose and access/cache/retention/output modes; exact corporate real cohort; true source cutoff/observation and permitted ordinary operation |
| HKEX | DI-specific authorised retrieval/reuse/link/export basis; correct inventory/date basis and complete issuer/window/revision closure; bounded qualified incremental operation |
| All | Actual shared-host headroom/recovery gate, source-scoped restore proof, mandatory checks/review/CI, latest-main merge, real backend/Worker/DO adoption and restored schedules |

These gates block only dependent collection, outputs or activation; they do not
justify stopping reversible schema/parser/adapter/UI/test engineering. If a human
decision is unavoidable, finish unblocked work first and present its exact intended
recipient/action or commercial/access choice with the concrete prepared artifact.
