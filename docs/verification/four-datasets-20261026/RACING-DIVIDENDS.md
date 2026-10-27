# Reported final dividends

This increment implements quoted final dividends from the existing bounded public
results collector. It is source-format and engineering qualification, pending a
checked release, actual accepted collection and independent production restore.
It does not complete sectionals or the remaining Racing families.

The operating basis is the owner's authorized implementation of ordinary public
factual racing results. This is not an HKJC licence or endorsement claim. Exact
English and Traditional Chinese current/archive result routes, dates, venues and
race numbers retain the existing URL validator. There is no new source, account,
provider quota, timer, redirect permission or public collection-on-read path.

## Fields and coverage

Select only the three-column final-dividend table headed Pool / Winning
Combination / Dividend (HK$), or its Traditional Chinese equivalent. Raw HTML,
incident narratives, images, videos, challenge participant strings and linked
challenge-detail pages are not retained or exported. Existing source observations
retain their URL, UTC capture time, byte count and SHA256.

Keep the reported pool label, raw combination, raw amount and exact decimal string.
Commas may be removed from the decimal representation; no rounding, combination
sorting, numeric conversion of identifiers or inferred payout tier occurs. A
stable quote ID binds the race, canonical pool label and whitespace-normalized
combination. Both language observations must reconcile every quote and numeric
amount. Each language's printed precision and labels remain available.

The inspected table explicitly labels HK dollars but does not state the stake
basis. `stakeAmount` and `stakeCurrency` remain null, `stakeNormalized` is false,
and no per-$10 return or odds history is inferred. WIN, PLACE, QUINELLA, QUINELLA
PLACE, FORECAST, TIERCE, TRIO, FIRST 4, QUARTET, numbered DOUBLE / TREBLE / DOUBLE
TRIO and SIX UP labels are translated without inferring additional semantics.
Explicit source rowspan alone permits inherited pool labels.

Recognized JOCKEY CHALLENGE / TRAINER CHALLENGE rows displaying only Details
links have no quoted monetary amount. Count them as `deferredNonmonetaryRows`,
separately from numeric `sourceRows`; their sum must equal `tableDataRows`.
Their names and links are omitted. Any other unknown pool, nonnumeric amount,
layout drift or bilingual mismatch makes this field family `unqualified`, with
null quotes, while valid core race results remain available.

Old normalized page caches have no retained HTML from which to extract dividends.
They produce `not_extracted`, with no extra source read or fabricated empty table.
Accepted historical versions remain immutable. `not_present` describes only a
captured page without the qualified table; it does not establish zero dividends.

## Serving and verification

The existing race-results REST and MCP responses carry the same observation.
The bilingual page renders source labels, combinations and amounts, with unknown
stake and omitted-link coverage stated beside the table. The real per-race ZIP
contains unchanged full JSON, runner-summary CSV, notice and checksummed manifest,
plus a schema and `dividends.csv` when numeric quotes are observed. Runner counts
and dividend counts remain separate. CSV consumers must import combinations as
text to preserve leading zeros and separators.

Tests cover exact decimals, explicit rowspan, missing/old cache semantics,
cross-race quote identity, bilingual mismatch, unsupported fields, hidden private
candidates, recovery then REST/MCP parity, actual ZIP contents/member hashes and
corrupt-payload rejection. Rendered tests use invented facts and no provider
requests. Real source qualification is separately recorded with source hashes
and the existing durable pre-request admission receipts; no fixture is described
as a source observation or public adoption.

A normally admitted fresh English/Traditional Chinese pair on 27 October checked
15 July Happy Valley race 9: 20 numeric quotes and two nonmonetary detail-link
rows. All 22 table rows reconcile. See
[racing-dividends-format-qualification-20261027.json](racing-dividends-format-qualification-20261027.json).
These private captures have no public dividend version. Eight rendered fixture
journeys passed at 320, 390, 768 and 1280px, with zero page errors or provider
requests; the second meeting correctly clears the first meeting's dividend table.
