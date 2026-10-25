# Working real archive; production activation pending

25 October 2026. The build uses the original already-released Webb archive and its
existing reuse notice. The earlier new-permission-first sequencing was corrected;
no provider outreach is required to implement this historical archive.

Implemented literal-only extraction, indexed source-scoped PostgreSQL loading,
SELECT-only reads, full restore qualification and compare-and-swap publication,
REST/MCP contracts, bilingual issuer/disclosure/detail browsing and bounded ZIP
exports retaining source notice/provenance. Raw source rows/dumps remain ignored.

Actual local results:

- Complete 12,416,843,125-byte SQL member SHA256 matched the audited original.
- All seven selected source-table censuses/checksums matched; 341,047 disclosures.
- 577,748,992-byte indexed model, 3,064 issuer identities; no orphan event/capacity
  parents. 145 absent revision serials remain explicitly unresolved.
- Independent physical PostgreSQL dump/restore compared every row of all seven
  database tables, including metadata, before local publication.
- Real SELECT-only HSBC query: 2,591 disclosures, first event 2003-03-31, latest
  2025-05-07. Real detail `webb:sdi:331188`; filing date remains null.
- Eight real browser journeys across EN/ZH and 320/390/768/1280px passed, including
  actual page navigation and 20-row ZIPs whose packaged checksums were verified.
- Eight synthetic browser journeys passed revision gaps, large numeric strings,
  unknown dates, pagination, failure-state clearing and download checksums.

See `real-extraction.json`, `real-query-proof.json`, `real-browser-receipts.json`,
`synthetic-browser-receipts.json` and [field/operations reference](../../data/webb-sdi.md).
Synthetic PostgreSQL tests exercise source identity, restored-content failure,
read-only grants, publication conflict, code reuse, tied dates, signed cursors and
REST/MCP parity on an actual PostgreSQL instance.

This receipt establishes a working local product. Production schema/data, offsite
copy/restore and gateway activation have not yet been performed for this archive.
The checked-in consumer flag remains off until those steps pass. Source-free
status does not claim data availability. Existing fresh official HKEX gates remain
independent. The shared release slot must be acquired before any merge/deployment.
