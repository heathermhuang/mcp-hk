# Census16 nested XML — build proof, 7 November 2026

Three exact frozen XML resources are ZIPs containing 23 / 19 / 25 inner ZIPs.
One bounded original-source inspection per resource returned HTTP 200 while both
qualification lanes were confirmed paused. Each inner archive contains native XML
and an XSD. Total expanded bytes across all three were 29,090,610. The existing
archive reader stopped at the extra ZIP layer; this was an implementation gap.
Original URLs, IDs, sizes and hashes remain in `results.json.gz`.

The exact dataset/URL/XML profile now requires native member and group choices,
for example `file:F101s.zip/Observation`. Root metadata lists actual file choices;
file metadata lists actual native XML groups. Neither counts as record acceptance.
Child actions retain full native paths and do not replace or borrow global choices.
The ordinary XML reader remains the record parser. Native strings, suppressed
values, leading zeroes, group names/case and source XML context remain unchanged.
Original XML/XSD member names and hashes are exposed as provenance. Dictionary
bytes are not interpreted as automatic semantic approval; file/language/period
and statistical normalization remain unqualified. Unselected members/groups are
not claimed as accepted records.

The reader permits the demonstrated second ZIP layer only. Cumulative expansion
stays within 32 MB, with the existing 1,000-member bound. Encryption, nonregular or
ambiguous/traversal paths, duplicate names, malformed archives, unexpected depth,
unconsumed prefixes/suffixes, unknown selectors and shape changes remain held.
Missing or inappropriate query selectors fail before provider access. Metadata
parsing stays off the event loop and inside the existing two scan/source slots.
The concurrency regression proves a third metadata download waits while two
parsers own those slots. No ordinary unrelated ZIP behavior or limits were widened.

The qualifier discovers intermediate file choices with schema operations and
queries only native group leaves. A whole-file transport failure holds remaining
sibling choices that use the same original URL; saved failures are reused rather
than retried through another selector or endpoint. Selected-group parsing/capacity
holds remain distinct. Its explicit three-resource cohort is verified against
the original frozen URL hashes and IDs; no native inventory entries were added.
Unavailable/restricted scopes are not made eligible by this adapter.

All 67 captured Observation scopes passed local HTTP/native MCP: 11,078 / 8,460 /
10,551 raw XML elements, 140 fixture reads, zero provider requests. Discovery parity
excludes only per-request checkedAt timestamps. A first harness attempt hit the
normal local HTTP limit; the successful run paced requests without changing its
identity or quotas. Afterward, the final capacity correction kept metadata parsing
inside the semaphore. Its concurrency regression and three representative captured
HTTP/native MCP scopes passed on that final code; the full 67-scope evidence remains
valid for unchanged record extraction. Both runs record runtime source hashes.
No simultaneous recovery of all record caches is claimed under the unchanged
4 MB row-cache and 50-variant/resource retention policies.

Required full checks, exact-head CI, coordinated release, every unblocked deployed
choice and fresh accepted backup/isolated recovery remain gates. Production still
uses the preceding notification release. RVD/Identify source failures, Hydro reuse,
other source/capacity/semantic holds and the complete wider programme remain open.
