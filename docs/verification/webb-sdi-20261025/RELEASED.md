# Real Webb disclosure archive released

25 October 2026. [Browse the archive](https://mcp.hk/hkex) in English or
[Traditional Chinese](https://mcp.hk/hkex?lang=zh-Hant).

The actual released Webb data is implemented and publicly queryable: **341,047
Form 3A directors' disclosures across 3,064 source issuer identities**, with
426,219 capacity rows, 345,355 event rows, original dictionaries and revision links.
Event dates in the release range from 1994-09-19 to 2025-12-24. These historical
records do not establish complete/current HKEX coverage or current holdings.
Filing/publication dates remain unknown; original FLOAT/DOUBLE representations
remain strings without a claim to recover original decimal input.

The existing original Webb reuse notice is retained in the package, public notice
route and every page ZIP. No new licence procurement or provider outreach was a
prerequisite for building this archive; no fresh HKEX collection was started.
[Source and field reference](../../data/webb-sdi.md).

## Released implementation

- [PR #81](https://github.com/heathermhuang/mcp-hk/pull/81): literal-only full-source
  extraction, indexed source schema, SELECT-only reads, complete restore gate,
  atomic publication, REST/MCP, bilingual browser and bounded page ZIPs.
- [PR #83](https://github.com/heathermhuang/mcp-hk/pull/83): qualified source
  activation, persistent Worker consumer flag, indexed archive page and isolated
  private-backend startup with regression/image smoke tests.
- Deployed gateway source: `84273bf3fef493f84b6db30222f903143f39a008`.
  Worker version `7a6467b4-1bf1-46f0-a100-1a4d4b2d1c0b`, 100%.
  Container application version 48; image SHA256
  `d8713b65865d6d3c150c5d8b5b94dcda27226c05d0ebe79386072f2ee5a930d6`.
- Private backend source: `cf0876e682f6f784a8cceca3286854ef9ec9940d` in its immutable
  release directory. Verified image SHA256
  `0ac6c341baf7aa2d6ae141c598490e3884531b3629c3aaab56644bfefbad7520`.
  The gateway merge adds sibling release documentation; application code matches.

Private diagnostics confirmed actual controller adoption and policy
`source-review-11`. Actual public archive HTTP and MCP verified container adoption;
release headers alone were not used as proof.

## Acceptance and recovery evidence

The full original source SQL checksum and all seven source-table censuses matched.
All archive data was loaded into the independent `webb_sdi` schema, under its own
PostgreSQL writer lock and non-login owner. The existing backend role received
SELECT only. The original offsite candidate was independently downloaded and
physically restored; every row of all seven database tables matched production
before atomic source acceptance.

The **fresh accepted** source backup includes its publication pointer and restore
proof: 37,477,564 bytes, SHA256
`bcf56786545247fed4f9f644fbc2ae577c97e4b020dacd0e6ef0b939cdbc5341`.
Its independently downloaded physical restore again matched every row of every
one of the seven production tables, including accepted metadata.

The gateway's separate fresh checkpoint was created at 08:37:01 UTC: 76,090,666
bytes, SHA256
`e129a648f02ea930452dbe990680ecff4aa2442faed67de7546a6deb69a2aa2c`.
Independent restore passed checksum, archive/database validation and ready state,
including 17,276 restaurant records and 18 population records. This SQLite
checkpoint does not cover PostgreSQL; the source proof above covers the archive.

Live acceptance passed on both public origins: source census, exact issuer
identity, signed pagination without duplicate rows, pinned details, original notice
checksum and preserved company archive/latest-observed views. The live MCP server
exposed 43 configured tools; archive status and full pinned detail exactly matched
REST. Fresh-HKEX data tools remained independently unavailable.

Eight live browser journeys passed EN/ZH at 320/390/768/1280px, including real
20-record ZIP downloads, all packaged file hashes and the original notice hash.
The same eight real local journeys and eight synthetic edge-case journeys passed.
Mandatory checks passed 499 Python tests (all PostgreSQL lanes included), 113
Worker tests, formatting/lint/types and CI for Python 3.10/3.11/3.12. The actual
backend image passed a read-only, no-network, non-root import test locally, on the
host and in CI.

All five configured schedules were restored and verified after adoption. A fresh
accepted checkpoint/independent restore and final ready/policy/lease checks passed.
Final source storage: 547,160,064 bytes; host free space: 53,776,486,400 bytes,
above the existing 20 GiB reserve. No new service or source collector schedule was
provisioned. Company source state, maintenance runners and the database/proxy
containers were preserved.

## Corrected rollout failure

The first backend attempt returned 502 because eager package import constructed
the public MCP gateway and attempted to create SQLite state in the private
backend's unwritable working directory. The previous immutable backend source was
rebuilt/restored and its HTTP health verified. The originally recorded image ID
was unavailable; an explicit rollback image tag is now retained.

The fix makes the legacy `mcp` export lazy. A clean-process regression failed
before the fix and passed after; explicit legacy imports still pass. The real
backend image now imports without writable gateway storage or networking. The
fixed backend's exact image, health, real source queries and both live company
views passed after rollout. No workaround changed filesystem privileges.

Public-safe detailed receipts are in [released/](released/). Raw rows, dumps,
credentials and full operator responses remain outside Git. The original checkout's
unrelated duplicate files were preserved; the final release used a clean temporary
clone. No blocking findings remain for this historical archive release. Fresh
filings, other DI forms and current holdings are outside its demonstrated coverage.
