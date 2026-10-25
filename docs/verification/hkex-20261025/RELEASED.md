# HKEX DI gated engineering release — 25 October 2026

PRs [74](https://github.com/heathermhuang/mcp-hk/pull/74) and
[76](https://github.com/heathermhuang/mcp-hk/pull/76) are merged. Deployed source is
`9e0c7be58760c56e392bcbfe0a53729586e45f96`. PR76 head
`8e720dc78712959f2b12499092643a698a63af00` passed all required CI; the final merged
head was checked again after preserving separately accepted maintenance-runner
fixes and SFC release receipts. The separate host runner was not redeployed here.

This releases the disabled source capability and qualification page. It is not a
live HKEX dataset. No HKEX issuer/window has been collected, source-qualified,
published, downloaded from offsite or observed in ordinary operation. The provider
request is [prepared and unsent](REQUEST-UNSENT.md). No public request can activate
collection/output, and a deployment flag does not substitute for a reviewed grant.

## Engineering and verification

The source-isolated schema, strict lossless normalized contracts, durable bounded
collector engine, independent inventory/detail/revision reconciliation, signed
versioned SELECT-only reads, shared REST/MCP/browser adapter, bilingual explorer,
offline export builder and full source-table dump/restore qualification are present.
Actual provider formats/route adapter, dictionaries and filing-window inventory
remain gated. Synthetic fixtures are not an asserted official response parser.

The mandatory installed pre-push hook ran `bash scripts/check.sh all` on the final
pushed head: **443 Python tests passed**, seven optional network probes skipped;
**all 49 PostgreSQL tests executed**, including **20 HKEX** and physical Enigma/SFC/
HKEX restore contracts; **112 Worker tests** plus formatting, lint, generated types,
TypeScript and discovery checks passed. Required CI passed on Python 3.10/3.11/3.12,
PostgreSQL, code quality, deployment and rendered browser workflows.

Eight synthetic EN/繁中 browser journeys covered 320/390/768/1280px issuer selection,
pinned notices, unknown dates, lossless numeric values, supersession/withdrawals,
focus, bounded tables, absent unqualified downloads/links and revocation. Existing
browser journeys passed. The final Python 3.11 production image passed a smoke test
with networking disabled. Local source-wide restores used invented facts; mocked
local headroom in those tests is not production capacity evidence.

Focused correctness/security/data review fixed SQL/resume/lock/restore/dispatch,
privacy/status, identifier round-trip and retention-expiry defects, and has no known
blocking defect in this disabled scope. Review and exact remaining activation gates
are in [REVIEW.md](REVIEW.md) and [ENGINEERING.md](ENGINEERING.md).

## Production scope and remaining gates

The existing curated host was inspected read-only: 55,215,316,992 free bytes,
6,528,998,423 database bytes, no granted advisory writer lock, US$24/month compute
configuration and backups enabled. The recorded approved cap is US$30/month; the
prior weekly-backup budget is US$28.80 before tax, not an independently reconciled
invoice. Existing address and offsite service failures were preserved for their
owning company-maintenance chat. No new source growth was allocated for any track
by this HKEX release, and no production HKEX schema/writer/timer or new credential
was installed. No `/opt/mcp-hk` checkout, host runner or accepted company pointer
was replaced. New source growth still requires current shared recovery qualification
and a measured complete pilot/WAL/capture/backup/offsite/restore allocation.

Backend/schema deployment must precede any future data consumer. The released
gateway is unconfigured and serves its source-unqualified contract locally, with
zero HKEX or curated HKEX backend requests. No current HKEX backend/schema adoption
is claimed. The independent PostgreSQL offsite download/restore and an ordinary
permitted source occurrence remain unpassed; gateway SQLite recovery cannot satisfy
them. Daily RPO and complete/current ownership or executed-trade claims are absent.

Source-qualified live acceptance requires an applicable route/mode grant and filing
inventory, then the real one-issuer/seven-day pilot and full closure, permitted
versioned download delivery, complete source offsite recovery, actual reader and
consumer adoption, real data/browser parity and a normal permitted refresh/restore.
If filing-date completeness cannot be established, that gate must remain failed;
any useful authorised event-window subset must be labelled separately.


## Observed rollout, live gate and recovery

| Component | Verified result |
| --- | --- |
| Worker | `56545b11-87ad-4695-8ccf-bc47cde43e78`, 100% |
| Actual controller | Source `9e0c7be58760c56e392bcbfe0a53729586e45f96`, `source-aware-ux-1`, `source-review-11` |
| Active data container | Application version 45; image `sha256:aa3ab60135282ea4c54fe1594bae7293dcb1bfcec5344fddb252cca740e78b43` |
| Runtime | Accepted base packs ready; real maintenance/seed leases clear at adoption and recovery checks |
| Public REST/MCP | Both origins agree on source-unqualified status; data modes denied; schema/discovery expose status only; 38 MCP tools |
| Existing company packs | Real pinned REST/MCP values match for `enigma251227-hk-v1` and `official-74c0460422870d185125947b48319d84` |
| Live browser | Eight EN/繁中 journeys at 320/390/768/1280px; no exceptions/overflow/download controls; keyboard retry works; zero HKEX provider requests |
| Schedules | All five checked-in schedules restored and verified |
| Fresh gateway backup | 76,405,523 bytes, created 25 October at 14:09:53 Singapore time |
| Independent gateway restore | Passed 14:11:11 Singapore time; exact SHA-256 `2a845d9dc3ee080f7bf714d263cd0c6d6a714fce1df52c56bf84f659347252e0` |

The shared slot was acquired after SFC released its own claim. Only resource cron
was paused, at 13:45:08 Singapore time; the full 15-minute propagation window elapsed
at 14:00:08 before rollout, and actual maintenance/seed leases were checked separately.
The immediate DO update setting existed only in the private temporary pause config;
the normal checked-in defaults remain intact. Worker/controller/image adoption was
verified directly, including real Python tool behavior, rather than inferred from
release headers. All schedules were restored at 14:09:14 and the fresh accepted
checkpoint was downloaded and restored in isolation. The owning claim was released
at 14:15:03 after recovery verification; it was never expired or stolen.

The normal restore implementation verified archive paths, capture hashes, SQLite
integrity and accepted packs. The restored snapshot retained 17,276 restaurant and
18 population records. This gateway snapshot does not contain curated PostgreSQL
or a live HKEX source. No HKEX offsite recovery, ordinary update or daily RPO is
claimed. The full synthetic source-schema dump/restore tests and both SFC/HKEX
migration orders are separate engineering evidence.

Rollback retains Worker `729490b3-34a1-4b1f-9316-c721676b1011` and the previous accepted
checkpoint `b06cbb12706030d66e486decf94c9f21f83d8cd94df83bd433f38bb10e1639f2`.
Restored gateway recovery and source-local compare-and-swap rollback/conflict tests
passed; a live production rollback was not performed. No schema/data reversal is
needed for this disabled gateway release. A future enabled source rollback must
also respect the then-current rights and compatible retained source version.

Machine-readable public-safe receipts are in [released/](released/). Credentials,
private captures, raw checkpoints, full operator responses and browser screenshots
remain in ignored owner-only local evidence storage.
