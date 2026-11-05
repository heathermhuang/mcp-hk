# HKMA native page-count correction

The current adapter treated HKMA `result.datasize` as a stable total for the entire
selected API. An exact official bank-branch request returned `datasize=1000` with
1,000 records at offset zero, then `datasize=51` with 51 records at offset 1,000.
Stopping after the first page therefore omitted published records while claiming
complete paging. Source byte hashes and unmodified compressed fixtures are retained.

The repair treats the count as per-page evidence, validates its exact integer type
and cardinality, follows offsets until an explicit empty terminal page and rechecks
the first and last nonempty pages. Repeated pages, malformed counts, provider denials, changed
boundaries and exhausted budgets fail before acceptance. Every read, including
rechecks, shares the existing 100-request and 8,000,000-byte budgets and a 120-second
complete-read deadline. The existing
100,000-row ceiling remains. Verification overhead can leave fewer requests for
data pages; a capped traversal remains an explicit capacity hold.

The response retains all original fields and records. `sourceMatched` counts the
observed reconciled rows, while `countEvidence.independentGlobalTotal` remains null.
No atomic publication or deduplicated bank/branch entity count is inferred. Existing
filters and language/segment values are retained. The provider's documented offset
and page-size parameters are described in the
[official API documentation](https://apidocs.hkma.gov.hk/documentation/).

`hkma-pages-2` changes the selection key so fresh legacy caches cannot bypass the
new reader. Capability projection keeps historical receipts visible and marks old
HKMA contracts for revalidation. Backend health exposes the actual contract.

The positive fixture replay returns 1,051 observed rows through both local HTTP and
native MCP despite a freshly seeded old 1,000-row cache; that old receipt remains.
Its permitted empty terminal response is explicitly simulated. The actual terminal
request at offset 1,051 returned HTTP 405 and a non-JSON page, so these observations
do not qualify a complete live source traversal. That exact hold is retained in
`hkma-source/offset-1051-hold.json`; no alternate route or retry followed the denial.
Additional regressions cover exact/empty terminal pages, changing first/last pages,
boolean/wrong counts, short intermediate pages with later records, repeated pages,
budget/deadline exhaustion, immediate denial and denied terminal requests.
Local source success does not clear the separate dated hosted HTTP errors. Actual
adopted HTTP/MCP source verification and fresh accepted isolated recovery remain
release gates for this implementation.
