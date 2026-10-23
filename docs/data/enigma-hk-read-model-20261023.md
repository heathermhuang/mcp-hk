# Enigma Hong Kong read-model qualification — 23 October 2026

**Locally qualified; no production publication.** [Machine-readable evidence](enigma-hk-read-model-20261023.json).

The original audited release was projected into typed PostgreSQL tables in 525.63
seconds. It contains 3,957,949 source entities, 7,786,192 identifiers, 7,929,688 name
facts (891,211 former-name facts), 559,372 officer appointments, 13,446 corporate
licence records and 565,646 licence relationships. All selected relationship
endpoints resolve through enforced foreign keys; dictionary references reconcile.

Scope counts overlap: 3,693,036 HK-domiciled organisations, 30,637 explicitly
registered non-HK organisations, 4,228 HK Main/GEM issuers and 5,570 SFC firms.
Referenced officers/staff and corporate officers close the graph; the importer
does not recursively include unrelated foreign-company appointments. No names
are merged, incorporation-number zeros are retained and no verified BRN crosswalk
is claimed.

All seven read-model table counts and constraints reconciled. There are 1,120
source officer rows whose start date exceeds their end date, and many unknown or
imprecise bounds. These remain original source claims. Responses expose the
qualification and reject exact `asOf` requests. No invalid parsed relationship
dates were observed in this selected projection.

The candidate used 6,252,027,904 bytes of table/index storage before restore (about
6.25 GB decimal). Its complete compressed backup is 398,652,591 bytes, SHA-256
`a2fa41b79d03283d3b659dbf2045ef65b8fa2cd594ae2200cd6028bb061c6330`.
The original disposable database was taken offline after retaining that verified
backup, aggregate inspection and source-fidelity evidence, preserving the 20 GiB
disk reserve. A fresh database restored the backup and matched all table counts,
constraints, dictionaries, temporal metrics and 30 ordered row hashes per table.
This proves local recovery under the measured environment, not offsite recovery
or all-row cryptographic equivalence.

The final normalizer separately matched 150 original source records across
organisations, people, appointments and both licence families. The full 15-table
67,329,696-row restored-source census still matches the previous audit. The import
manifest retains the byte hash of the implementation that ran it. Later edits
formatted files and hardened source census/identity checks and connection bounds;
the fact transformation and schema are unchanged. The final normalizer and
full-model reader/restore paths were reverified without reimporting unchanged data.

Measured actual SQL plans used indexes for bilingual prefixes, literal `%_`, an
existing exact identifier and name/officer/licence reads. The larger relationship
fanouts were tested. Execution times ranged from 0.04 to 32.273 ms in this local
run. These are bounded probes, not throughput or production-SLA measurements.
A real loopback HTTP server matched the query library on the full model and
returned nonempty officer/licence families. Authentication, missing IDs and
unsupported `asOf` behaved as expected.

The built container passed authenticated health/read requests as non-root UID
65532 and excluded the private archive/cache. Compose configuration validated.
The PostgreSQL fixture originally reused the caller's publication pointer; a
forced database-isolation regression failed before the fix (1/1) and passed after
it (1/1). Each test now owns an entire database. The full-model pointer survives
the complete suite. No timeout or assertion was loosened.

Final local checks: 300 Python tests passed, seven pre-existing optional network
checks skipped; all seven PostgreSQL contracts ran, including physical
backup/restore and real statement/lock timeouts. Formatting/lint, Worker types and
all 92 Worker tests passed. See the PR for CI on its exact commit.

Production hosting/cost, offsite recovery, public gateway/MCP/catalogue/UI
integration and current official-source updates remain unqualified. Keep this
multi-GB model outside the existing gateway checkpoint.
