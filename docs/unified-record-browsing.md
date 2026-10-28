# Integrated record browsing

The company, disclosure and corporate-licensing pages use one primary search,
result list and detail presentation. `unified-records.js` adapts the existing
accepted-reader APIs; it starts no source collection and changes no published
source data. Racing uses the same page shell, colour tokens, type scale and input
controls through `records.css`.

`RecordFeed` maintains independent versions and signed source cursors. A page is
bounded to each reader's returned page; the merged page is sorted locally and does
not claim a global chronology across different source orders. Shared URLs preserve
these independent versions and page inputs. A failed source is visibly unavailable,
never an empty match. Retrying reuses successful page data. Obsolete requests cannot
replace a newer query. Full source explorers and complete downloads remain under
the source-coverage disclosure and load only when opened; original detail URLs
still work.

Names and stock codes do not establish identity. Companies with different source
identifiers remain separate. Exact CE references and exact disclosure serials can
combine source variants without discarding either original statement or its dates.
Reused stock codes require an explicit issuer choice when ambiguous. Unknown event,
filing and summary dates remain distinct. Source attribution is visible with results;
full provenance and unchanged original data are available in record details and
source-specific ZIP exports. This UI integration does not qualify missing source
families, fill an unobserved period, or establish current registration/licensing or
ownership status. REST and MCP contracts remain unchanged.

Verification uses `record-feed.test.mjs` for identity, version, cursor, cancellation,
retry and checkpoint invariants. `unified-records-browser.mjs` tests the main flows,
actual downloads, composite-page reload, four widths and both languages against
synthetic accepted-reader responses. Existing source browser suites explicitly open
the secondary tools through `openSourceExplorer`. These fixtures test presentation
and client state; they do not establish source acceptance or production adoption.
