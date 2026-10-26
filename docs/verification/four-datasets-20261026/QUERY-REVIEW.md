# Company full-state prefix-read qualification repair

26 October 2026. The actual 139 MB source upload/download succeeded after PR 93.
Its independently restored database matched all source-table fingerprints and raw
checksums, then failed the unchanged two-second SQL gate in a staged grouped prefix
read. PostgreSQL logged that exact query shape on the original attempt and on the
read-only diagnostic. The failed job and restored clone remain retained.

Plans show ordinary comparison operators missing the existing `text_pattern_ops`
indexes. The grouped query also carried full JSON facts through matching/sorting,
and could choose an expensive entity-order scan for broad Chinese prefixes. The
repair uses the existing indexes' bytewise prefix operators, materializes only
matching identity/capture keys, applies accepted membership before limiting unique
company IDs, then fetches the newest matching fact for each returned identity.
The serving reader and staged qualification share that exact read shape. No index,
schema, source quota, transaction timeout or p95 threshold is changed.

On the retained production restore, fifteen numeric/Chinese/English reads passed
with stable result hashes at 314 ms p95. The complete verifier then passed all
table fingerprints, all 892 raw captures and the representative detail/identifier/
prefix/pagination checks at 376 ms p95 and 392 ms maximum for 72 qualified week
pairs. This remains a 72-pair qualification, not the original 94-pair target.

The regression covers unpublished earlier identities that must not consume the
page limit, newest matching bilingual aliases, pinned pagination, fullwidth Latin
normalization and literal percent/underscore/backslash prefixes. Existing source
identity, publication, rollback, address and real PostgreSQL contracts also pass.

An operator can requalify the retained exact dump after the repaired code is
deployed. A separate `retained_restore_check` receipt preserves the failed job and
does not re-upload source bytes or claim an ordinary daily occurrence. It requires
the latest exact dump checksum/prefix, current schema, unchanged accepted pointer
and effective membership, current query-code hash, all-table/raw/read-only checks
and the unchanged subsecond p95. A changed dataset or failed proof cannot reopen
growth. The old upload time and its qualification/daily distinction remain intact.

Focused correctness/security/data-semantics review: no blocking findings. The
complete published 94-pair acceptance, ordinary source/offsite occurrences and
actual same-version REST/MCP/browser/ZIP matrix remain outstanding. This change
repairs the measured blocker without certifying the broader programme.
