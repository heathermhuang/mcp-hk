# Enigma source audit: 23 October 2026

Status: source archive restored and sampled import fidelity verified. This is offline preparation for corporate data packs, not a production data release. [Machine-readable aggregates](enigma-audit-20261023.json), [operator workflow](../enigma-audit.md), [original attribution notice](../../src/mcp_open_data_hk/webb-site-NOTICE.txt).

## Observed source

The original public `enigma251227.7z` release was acquired with resumable checkpoints and verified at 1,721,680,391 bytes. Acquired SHA-256: `9c2c42ae5e762d34b60954f43b37199b92b546033e229a292ed08b76323f6de2`. The checksum identifies these downloaded bytes; it is not a publisher signature.

The archive lists three SQL members: data (12,416,843,125 bytes), structure (449,550 bytes) and triggers (24,907 bytes). Structure and data were extracted with size/integrity checks; source triggers were not executed. The dump identifies MySQL 8.0.37. All 187 table definitions and all 151,145,202 source rows were inventoried. There are 186 data-bearing tables; `errorlog` is empty.

## Restored audit projection

Fifteen allowlisted tables were restored into a separate, disconnected, resource-limited MySQL container. Every table's committed count matched the parsed source count. The audit restored 67,329,696 projected rows, mostly global records; this is not a count of Hong Kong companies.

| Family / source table | Verified rows | Meaning |
| --- | ---: | --- |
| `organisations` | 19,734,419 | Global source entities, including 3,693,036 Hong Kong-domiciled entities |
| `people` | 14,611,943 | Projected name/licence-reference fields; identifying/birth/internal fields excluded |
| `namechanges` | 2,502,870 | Previous names and source change dates |
| `directorships` | 29,848,020 | Global officer/other-role records, including non-Hong Kong relationships |
| `licrec` | 565,646 | Individual/firm/activity/role intervals, not distinct people |
| `olicrec` | 13,446 | Organisation/activity intervals, not distinct firms |
| Nine supporting dimensions | 53,352 | Domiciles, entity types, dissolution modes, positions, activities, date precision, issues and listing history |

The successful restore/count/date audit took 840.21 seconds in this local environment. Native extraction observed roughly 0.86 GB resident memory; the database had an enforced 6 GiB memory limit and no external network or published ports. These are audit resource observations, not production query benchmarks or a host quote.

## Source-fidelity qualification

All 190 sampled records matched the original source dump after comparing equivalent timestamp fractional-second rendering:

- 100 entities: 20 older Hong Kong entities, 20 recent entities without a recorded dissolution date, 20 with a recorded dissolution, 20 bilingual-name entities, and 20 HK-listed offshore issuers.
- 30 name-change records, 30 officer records and 30 licence intervals.
- Source IDs/record values stay private; the report retains sampled field names and ID-set hashes.

The comparison caught MySQL JSON adding `.000000` to timestamps. Canonical comparison removes only redundant fractional-second zeroes; a nonzero difference still fails. It does not rewrite the imported facts. A regression test protects this distinction.

Acquisition/inspection/extraction, literal-only SQL parsing, privacy projection and credential/isolation guards have focused tests. The current package also includes the original notice and exposes the operator CLI. All failed/interrupted attempts and their receipts were retained privately; none became accepted results.

## Qualifications for the next projection stage

- This is a historical archive. Source updates in the restored tables reach December 2025; checking/downloading it in October 2026 does not make those observations current.
- `incID` is a domicile/source registry identifier. A complete BRN crosswalk is not established.
- `PersonID` spans entity and human identities; the `persons` table is an ID registry, not the human-name table.
- Company-name change dates, officer precision codes and unknown interval bounds must retain their original meanings. Raw global ranges include very early, future and sentinel-like years; they are not a Hong Kong coverage claim and must not be silently repaired.
- Hong Kong-domiciled entities alone exclude HK-listed offshore issuers. Production selection needs explicit relationship closure and separate legal-entity/type rules.
- Row-count reconciliation and sampled import fidelity do not establish exhaustive foreign-key integrity, complete current government coverage or parity with Renavon's later registry/property/odds additions.
- HKIDs, ID-source links, birth/death fields, sex, titles and internal user/search fields were excluded from the restored `people` projection. Original SQL, credentials and raw samples were not committed or published.
- The read model still needs Hong Kong subset normalization, exhaustive accepted-relationship checks, indexed PostgreSQL query qualification and a measured production sizing/cost proposal. No production backend, paid resource or public dataset was deployed by this audit.
