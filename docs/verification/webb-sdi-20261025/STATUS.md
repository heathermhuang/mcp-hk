# Released: working real Webb Form 3A archive

[Live explorer](https://mcp.hk/hkex) · [Release report](RELEASED.md) ·
[Field/API/operations reference](../../data/webb-sdi.md)

All 341,047 historical disclosures are publicly queryable through the bilingual
browser, REST and MCP. Source event dates extend through 2025-12-24; this is a
Form 3A archive, not complete/current HKEX coverage or current holdings.

The build uses Webb-site's actual already-released data and retained reuse notice.
A new licence was not a prerequisite for this archive build. No provider request
was sent and no fresh HKEX collection was started.

Production source acceptance, complete independent offsite physical restore, live
REST/MCP parity, eight bilingual live browser/download journeys, all five restored
schedules and a fresh independent gateway restore passed. The startup failure found
during rollout was corrected, regression-tested and verified on the actual backend
image. Existing company views passed live regressions.

PRs #81 and #83 are merged. Deployed source is
`84273bf3fef493f84b6db30222f903143f39a008`; the final evidence update is documentation.
See [released/](released/) for inspectable public-safe receipts. Raw data and
operator credentials remain outside Git. Fresh official HKEX coverage remains a
separate workstream rather than a blocker on the working historical product.
