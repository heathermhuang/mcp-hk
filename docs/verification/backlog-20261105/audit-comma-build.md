# Audit accounts object framing — build proof, 6 November 2026

Resource `656fde3a4a402d2e33d856f2619a9ec3` remains an internal reader gap in the
[reader-contract release](reader-contracts-release/README.md). The captured original
`https://www.aud.gov.hk/datagovhk/accounts-certified.json` response contains 1,337
strict JSON objects separated by commas without an enclosing array. It is 225,898
bytes with source SHA-256
`b93b1345d3bd9a1cac5d486a0dcabb0905247434f47ead08178afd7f5f56a51d`.

The extension recognizes this framing only at that exact Audit Commission URL.
Every object, separator and remaining byte must parse. Trailing/repeated commas,
mixed adjacent/comma framing, suffixes, duplicate keys and malformed arrays remain
errors. Valid ordinary JSON arrays continue through the existing reader. Other
Audit object streams retain their existing framing rules. Original source bytes
remain the version/hash authority; field names, strings, values and order are kept.
No fiscal-period normalization, dataset/entity equivalence or semantic binding is
introduced, and all existing source/row/field/cache limits remain unchanged.

The complete captured response now passes local HTTP/native MCP replay with 1,337
original objects, one fixture read and zero provider requests. This is dated replay
proof; production still has the recorded parse hold until the checked release.
Regression tests cover the positive framing, original hashes and raw years,
ordinary JSON arrays, wrong-source boundaries and incomplete/ambiguous framing.
Hosted source/client validation and fresh isolated recovery remain required.

DEBUG REPORT

- Symptom: the registered Audit accounts source retains `SOURCE_PARSE_ERROR`.
- Root cause: its top-level objects use comma separators, unlike the other Audit streams.
- Fix: a complete comma-framing mode only for the exact accounts URL.
- Evidence: all 1,337 captured objects and the original hash match local HTTP/native MCP.
- Regression test: `tests/test_resource_serializations.py` accounts framing cases.
- Status: build/replay verified; deployment and fresh recovery pending.
