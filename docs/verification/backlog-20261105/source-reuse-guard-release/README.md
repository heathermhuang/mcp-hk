# Source reuse guard — released 6 November 2026

PR [#173](https://github.com/heathermhuang/mcp-hk/pull/173), including the guarded
reader work from #170/#172, is deployed at `477d6692f143c5f77716c92e5bdb476e44ab7789`. All five exact-main
workflows passed. Actual Worker `b47da198-b6cf-4ac6-8847-f2fb4b80df10`, controller, immutable
image and native application/running instance version 85
were verified with readiness. An initial local source-selection assertion stopped
candidate creation; the unused build was retained and the image rebuilt from the
asserted source before registry publication or activation.

All three Hydro metadata interfaces matched HTTP/native MCP. Their record operations
returned `SOURCE_REUSE_REVIEW_REQUIRED` and every record capability remained held.
No Hydro data access or source reuse permission was activated. The endpoint notice
and catalogue terms leave the public API reuse basis unverified; owner clarification
remains pending. Source validation receipts and the software parser remain distinct
from reuse qualification. Pinned cached versions cannot bypass the default guard.
No request parameter or environment flag grants permission.

Required point, selected-resource, three-operator transport, scoped-action, published
interface, recycling and HKSTP live checks passed. The existing source/field/cache/
variant/quota and 150/500/750 MB recovery limits stayed unchanged. Fresh accepted
archive `ec59edbeb7880e36c368c2d79f03b17f708d6b2ee2162790fb910a31681b55c8` was independently retrieved from immutable
R2 and restored: 120,748,826 archive / 361,431,040 SQLite /
392,586,323 total bytes. Checksum, SQLite integrity, captures, accepted
packs, source registry, inventories and retained bindings/facts passed. Isolated
HTTP/native MCP reproduced the Hydro hold and all required legacy recovery checks
with zero provider attempts. No expired transport response is called current service.

Only resource cron was paused; native reads verified the original five and temporary
four schedules, full propagation elapsed, and leases cleared naturally. Pre-backup
restored before deployment. Actual adoption was observed without lease clearing.
All five schedules were restored/read back, final health passed, and only the owned
release slot was closed. Existing source processes resumed or retained their exact
terminal reasons; no saved source denial was retried.

Report window 1 stopped at its explicit 2,000-operation bound. A zero-request traversal
identified the next unsaved scope and the current accepted producer checkpoint
remained below the unchanged 130 MB bulk guard. A separate maximum-500 window archived
the original journal and reused all saved receipts. It stopped after 12 operations
on internal `SERVICE_RECOVERING`; the next resource request was unmade. The canonical
failure remains. Native instance state was running since 13:32, while gateway code
also maps generic transport/non-JSON errors to that recovery label. The precise
request failure is unverified. Its exact scope was absent from bounded restored
variants, which does not establish an execution stage or justify another source retry.

The full frozen programme, wider graphs and independently supported semantic tasks
remain open. Hydro's source-rights hold, Census builder redirect limits, exact format/
capacity/source reasons and unqualified semantic scopes are preserved.
