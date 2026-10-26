# Current HKEX summaries: implementation verification

26 October 2026. Current task: get published HKEX DI summary facts and maintain them
with deterministic scheduled code, while preserving the historical Webb archive.

The public source menu currently points to 23 October 2026. All four latest pages
were fetched normally: 169 shareholder, 66 director share, 10 associated-corporation
summary rows and an explicitly structured empty debenture report. A bounded seven-
calendar-day collector staged 1,004 observations across four published dates,
20–23 October. Unavailable older pages remain gaps, not inferred zero filings.

Actual local PostgreSQL whole-schema physical restore compared all seven tables
and the request sequence before local publication; SELECT-only queries passed.
Synthetic source/PostgreSQL contracts cover holds, unchanged 304s, quotas, writer
locks, source date/identity drift, unknown dispatches, pinned cursors, recovery gates
and exact REST/MCP parity. Eight real-data and eight synthetic responsive EN/ZH browser/download journeys passed at 320/390/768/1280px. ZIP contents and packaged checksums were verified.

Production deployment, timer activation, actual ordinary occurrence, and offsite
recovery are not yet established by this preparation receipt. The consumer flag
remains off in checked-in deployment configuration until backend/source acceptance.
No HKEX provider licence or permission grant is claimed. See
[the field/operations reference](../../data/hkex-daily.md) for exact scope and use basis.
