# Explicit array discovery for streamed JSON

Nine frozen JSON resources in four original residual groups returned HTTP 400
`RECORD_PATH_REQUIRED` from actual hosted schema requests. The large-file reader
required a selection but provided no source array choices. Exact receipts are in
`streamed-json-discovery/before.json`; none establishes accepted records.

The repair scans the entire JSON document with the existing streaming parser,
without building record bodies or selecting an implicit default. It advertises
arrays reachable through supported object-key paths, excluding arrays inside
record arrays and keys the existing selected reader cannot address. Unsupported
object-key paths have an explicit count. Duplicate keys, malformed tails and the
existing depth/field bounds fail before choices are published. The source file is
closed on discovery success or failure. Choice metadata retains the existing
100-choice display and 1 MB global storage bounds; truncated choices stay explicit.
Metadata remains unverified and does not create accepted record variants.

A separate local attempt to inspect the official catalogue source stopped at the
existing `UNSAFE_SOURCE` network guard. It was not bypassed. Tests use a small
synthetic structural reproduction of the demonstrated reader branch; these are
not claimed as captured official records. Actual post-release qualification subsequently passed all 13 advertised arrays
through HTTP/native MCP, plus fresh isolated recovery. See
`json-discovery-release/` for the independently recorded release evidence.

Separately, all 84 explicitly published historical workbook sheets now have actual
HTTP query receipts with complete-source schema, integer total and one returned
item (or none for a zero total). The older artifact established parsing/counts;
this adds explicit query-operation proof. E101e still returns 22 rows through the
connected native MCP tool after the HTTP cohort. The summaries retain receipt and
returned-item hashes without publishing record bodies. The unchanged 50-variant
retention bound does not retain all 84 choices simultaneously. These are raw grids,
with zero new semantic bindings or distinct-dataset operation gains.

Eight exact gateway-recovery operations passed a single recheck after actual
health/readiness passed. Their earlier responses remain in checksum-addressed
history; native source denials were not retried. Broader qualification remains open.
