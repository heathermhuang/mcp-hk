# Recycling published CSV — build proof, 6 November 2026

Original resource `bba25323baf621535677e9a743b0923b` advertises CSV at
`https://www.wastereduction.gov.hk/zh-hk/resources-centre/recyclable-collection-points-dataset`,
which returns an HTML index. The captured primary page publishes one CSV link:
`https://www.wastereduction.gov.hk/sites/default/files/wasteless260708.csv`.

The original link returned 4,377,639 bytes and parsed as 9,735 raw rows within the
existing source limits. Source SHA-256:
`62c7700f319d1ecfa744627246c01e840a3807a71f9f25184636af3b91f31753`.
This is dated source evidence, not a new current-service or geographic qualification.

The file selector recognizes only this exact index and its current same-origin
`/sites/default/files/wasteless[0-9]{6}.csv` links. It requires an explicit published
file choice, preserves original-page/file provenance, and identifies the catalogue
format as CSV. Unknown/unpublished links and workbook/map selectors remain invalid.
The existing Census rules remain distinct. Index reads and invalid input cannot
clear an actual file-access denial. No filename date, coordinate reference system,
canonical collection-point identity or active service status is inferred.

The complete captured page/CSV passed local HTTP/native MCP replay: 9,735 rows,
matching data/version and original source hash, zero provider calls and three
fixture reads. Ordinary CSV reader versioning is retained alongside the original
content hash. All source/row/field/cache/variant and recovery limits are unchanged.
No new native inventory entry, binding, credential, service or scheduler is added.

Tests cover published-only URL/filename boundaries, explicit choice, original
values/provenance, correct format metadata, invalid selectors and unavailable
nearby semantics. Exact-head CI, hosted qualification, coordinated release and
fresh isolated recovery remain required. Wider frozen work and source holds remain.
