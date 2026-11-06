# Census16 native XML selectors — released 7 November 2026

PR [#183](https://github.com/heathermhuang/mcp-hk/pull/183) is deployed at
`910c117c0eac22ed4122fa88ea22d0727052713f`. All five exact-main workflows passed. Actual Worker
`763099e6-459b-459a-9785-00968c74407d`, controller, pinned image and native application /
running instance version 89 passed adoption/readiness.

The three original resources expose actual native file choices (23 / 19 / 25)
and native XML-group choices without counting discovery as record acceptance.
The explicit hosted scopes in `census-live.json` passed HTTP/native MCP with raw
row counts [57, 100, 108]. Selection is caller-specified; native
member/group names, source bytes/version hashes and XML/XSD provenance remain.
Source values, dictionaries and unselected-group summaries are not normalized into
statistical estimates, unique entities or equivalent files/languages/periods.
All 539 advertised native XML groups parsed from the captured bytes without
provider calls; this also includes dictionaries/metadata groups, not just observations.
The full 67-scope captured HTTP/MCP replay is build evidence, not 67 hosted acceptances or
simultaneously recoverable record caches. Other unblocked native groups remain a
qualification task in the explicit frozen-ID cohort.

A separate offline storage trial accepted all 539 captured groups into a full
accepted-checkpoint copy, then checkpointed/restored it. The 123,941,766-byte archive
fit the unchanged bulk guard. Unrelated version/schema/count facts for 61,889
variants, 5,048 native datasets, accepted packs and six point bindings survived.
Each of the three resources retained 50 variants; row cache was 3,540,553 bytes and
option metadata 999,954 bytes. This is a measured isolated result, not a forecast,
production acceptance or simultaneous recovery of every record cache.

The archive adapter is limited to the exact source profiles and demonstrated
second layer. Expansion/member/row/field/response bounds, two scan/source slots,
1 MB option metadata, 4 MB row cache and 50 variants/resource remain unchanged.
Unknown, encrypted, malformed, ambiguous or over-budget input remains held. Root
and child options stay separate; the qualifier traverses intermediate choices
before querying leaves. A recorded whole-file transport failure holds sibling
requests for that original URL instead of retrying it through another member.

A fresh pre-deployment checkpoint was retrieved and restored before rollout.
After natural 601-second expiry, accepted contexts were staged without modifying
clocks, validation timestamps or TTLs. This does not force a provider download for
unexpired caches. Staged versions can differ from earlier live versions. Fresh
accepted archive `b5042edb13cb51eca51eefaf13a410c36b28d4d05e7806110d66f9ffea206cf7` was retrieved from immutable
R2: 123,689,142 archive / 366,432,256 SQLite /
397,587,539 total restored bytes. Checksum, integrity, captures,
accepted packs, registry, inventories and retained bindings/facts passed. The three
staged native XML scopes matched isolated HTTP/native MCP with zero provider
attempts. Other available legacy checks and staged recovery also passed. Expired
transport observations are not current-service evidence.

The prior RVD028 and Identify record failures were not retried unchanged. Current
readonly HTTP/native MCP metadata and fresh restored metadata were verified;
`known-source-holds-live.json` records the observed state rather than inferring
availability or current record recovery from old accepted facts. Full legacy-record
clearance remains false. Hydro records remain denied pending reuse clarification;
GML empty placeholders and other unsupported semantics remain unqualified.

The first live sequence reached the existing public HTTP rate limit during a
parameter-discovery request. The 429 status/log was preserved, although its body
was not retained. Passed steps were reused; only remaining cases resumed after
a full natural budget window, with pacing, identity and quotas preserved.

The earlier HKSTP version pin returned HTTP409 during context staging. Readonly
metadata showed a newly accepted, queryable 501-row source response with the same
schema. The current accepted version was staged and recovery compared against it,
not against the earlier live hash. The first error body was not retained; that
limitation and the unchanged successful checks remain recorded. No source failure
was relabeled as empty data and no validation timestamp was rewritten.

Only resource cron was paused, with native schedule read-back, full propagation
and natural maintenance/seed lease clearance. All five schedules were restored and
read back; final health passed and only the owned release slot closed. Following explicitly approved launch-first steering, one-off qualification
processes ended at their saved boundaries after the slot closed. Their receipts
and terminal journals are retained for full-backlog follow-up; the existing
configured production schedules remain in place. No new
source permission, credential, provider identity, quota or service was added.
The 150/500/750 MB recovery limits and 130 MB bulk guard are unchanged.

The saved-receipt graph audit found zero known missing operations among 1,148
eligible frozen ArcGIS selection resources (990 visited, 158 with individual
failures). The two other frozen ArcGIS family members retain their separate
SOURCE_API_ERROR / SOURCE_UNAVAILABLE routes in `arcgis-nonselection-members.json`;
this does not qualify all 1,150 family representations. Other family graphs and
source/semantic reasons remain open.

The original full programme remains unfinished follow-up work. Bulk frozen
selection expansion, optional adapters and additional semantic bindings are
deferred from the launch critical path. Launch acceptance is assessed separately
against this frozen release, reusing valid unchanged CI/client/recovery evidence.
This release does not complete the full backlog.
