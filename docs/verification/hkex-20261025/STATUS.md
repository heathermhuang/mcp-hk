# HKEX DI execution — 25 October 2026

Owner chat: `01a1716d-9304-7231-85ce-7fbc21c764de`.
Isolated branch: `codex/hkex-di-20261025`; baseline `9521ef6857e92250d35b45dca09337eb328ed3d2`.
Reviewed contracts are copied into `docs/designs/hkex-20261025/`.

- [x] Read current implementation instructions and production/read-model/UX receipts.
- [x] Isolated checkout; preserve primary and sibling work; install required push hook.
- [x] Search project permission evidence and current official service documentation.
- [x] H02 source-isolated schema, policy, identities, typed interests and revision closure.
- [x] H03 normalized intake and bounded durable engine (actual provider adapter gated).
- [x] H05 private/shared reads, gated discovery and offline exports (live download publication gated).
- [x] H06 bilingual issuer/filing/revision UI and honest unavailable state.
- [x] H07 checkpoint/unchanged comparison and complete source dump/restore plumbing; actual ordinary/offsite operation gated.
- [ ] H08 focused correctness/security/data review, fixes, exact HEAD checks and CI.
- [ ] H09 shared merge slot and disabled integration release, where recovery permits.
- [ ] H04/H09/H10 authorised real pilot, live data activation, ordinary update/restore.

## Source decision

Existing repository and hk-app research/planning records were searched for HKEX,
DION, licences and permission. The only project-owned permission artifact is the
UNSENT brief in `docs/data/qualification/company-permission-briefs.md`; no grant was
found. Stripe Directory CLI/connector is unavailable; public Directory documentation
was attempted before the official documentation fallback. No notice/listing/detail
collector, browser workaround, source outreach, purchase or contract acceptance ran.

Current official documentation checked on 25 October 2026:

- [Terms](https://www.hkex.com.hk/global/exchange/terms-of-use?sc_lang=en), updated
  19 August 2025: sections 4–5 restrict linking, programmatic retrieval, compilation
  and redistribution without express permission or applicable separate terms.
- [List guide](https://di.hkex.com.hk/di/notes/NSAllFormList.htm): event-date ordering,
  pagination and persistent amendment/supersession/withdrawal identities. This guide
  does not establish a complete filing-date inventory or collection permission.
- [DION FAQ](https://www2.hkexnews.hk/-/media/HKEXnews/Homepage/Shareholding-Disclosures/Disclosure-of-Interests-Online-DION-System/dion-faq.pdf),
  updated 14 February 2026, is service documentation, not a reuse grant.

All source/output modes remain unknown and disabled. Exact official response
schemas, form/code dictionaries, routes, filing inventory, rights and schedule must
be qualified before activation. Offline normalized JSON fixtures describe our intake
contract; they are not an asserted parser for an uninspected provider response.

No real issuer/window is selected before a permitted deterministic inventory exists.
No timestamps are invented. No live acceptance or daily RPO is claimed.

Implementation and activation details: [ENGINEERING.md](ENGINEERING.md).
Focused review and fixes: [REVIEW.md](REVIEW.md).
Exact external decision: [REQUEST-UNSENT.md](REQUEST-UNSENT.md).
