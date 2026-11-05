# Census task equivalence and exact capacity holds

This audit covers exactly 1,770 frozen XLSX-labelled `web_table.html` candidates
whose earlier receipt was `needs_adapter`. It does not include the 162 issue-scoped
`wbr.html` report resources or unrelated workbook failures.

The read-only audit used accepted checkpoint
`00ea623ecf9b153b6ccb852549e6535cd22aade6e197e09175b2d8aa0ed50454`.
An alternative qualified only when its official table ID, explicit language and
`full_series=1` matched the candidate, its resolved official API endpoint matched
that same identity, and its accepted schema proved `C&SD tables`,
`complete_api_table`, a complete response and a native matched count equal to
accepted rows. Other parameters/scopes and languages were not treated as equal.

1,623 candidates have a dated accepted alternative under those exact criteria.
The audit made zero provider requests or source-status writes. Their last
validation times and accepted versions remain in the per-candidate evidence;
current upstream availability was not rechecked. This is existing API-table task
coverage, not source workbook-file, formatting or workbook-specific footnote
equivalence. It does not turn the original resource's old failure into acceptance
or claim any new dataset gains.

The remaining 147 candidates, spanning 50 native dataset memberships, each received
one bounded schema request through the already released adapter. All 147 returned
HTTP 422 `SOURCE_TOO_LARGE` at the unchanged 8,000,000-byte decoded-response limit.
The resumable execution saved its first 100 outcomes and visited only the remaining
47 on the next invocation. These are exact internal capacity holds, not provider
refusals, successful empty tables or repeated failed reads. No budget was raised.

Exact dated adapter matches are in
`wfs-release/census-adapter-task-audit.json.gz`; individual terminal source/URL,
selection, timestamp, duration and error receipts are in
`wfs-release/census-decoded-response-holds.json.gz`. The wider selected report and
raw-workbook graphs remain separate and unfinished.
