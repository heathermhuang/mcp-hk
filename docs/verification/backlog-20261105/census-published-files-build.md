# Census published-file selection — build proof, 6 November 2026

The three original 2021 Census district-profile resources advertise XML but point
to HTML pages. Each captured primary page publishes fourteen file links: seven
workbooks and seven archives labelled CSV by the publisher. Their file URLs are
choices, not accepted records or evidence of representation/language equivalence.

The selector is restricted to those three exact pages and their current published,
same-origin `/doc/*_21C.xlsx` and `/doc/*_21C.zip` links. `hk_resource_schema` lists
explicit `recordPath` file choices. A caller must choose a published file; its
workbook sheet actions retain that file context. Child choices do not replace the
root file list. Unknown URLs/files, query/fragment links, missing selections and
inapplicable sheet/map selectors cannot trigger arbitrary file reads. Index reads
and invalid caller input do not clear a recorded source-file denial.

A bounded native file investigation used the original page links and normal
DNS-pinned fetch under maintenance gates. The DC archive is 21,026 bytes, expands
to one 78,163-byte CSV, and parses as 75 raw rows. The workbook is 76,097 bytes,
expands to 467,910 bytes, has one `DCD` sheet and also parses as 75 raw rows. Headers
differ between the formats. Secondary headers/notes and generated blank-column
labels remain visible; these row counts are not qualified observations, district
counts, source-file equivalence or a new geographic binding.

Captured file SHA-256 values:

- ZIP: `9e075657e4933f5a05ecb2256cc04d94728fd650ef18f16ad14727da218c9600`
- XLSX: `a1b1d4f13bc5ad178f37d65d078bbb72d51c16a4393ec6982505ccc5bc850028`

Both captured files passed local HTTP/native MCP replay through the exact original
English resource. All fourteen discovery choices matched, with separate natural
metadata observation times. The two 75-row scopes preserved their original file
hashes and original-page provenance with zero provider requests during replay.
The other twelve files and the two other original language resources still need
individual hosted source/query proof. No new native dataset/resource is registered.

Source/expansion/row/field/cache/variant limits are unchanged. Parsing is offloaded
from the event loop. Tests exercise published-only choices, explicit selections,
file/sheet context isolation, raw values, provenance, invalid selectors and
preserved access holds. Full checks, exact-head CI, coordinated release, actual
hosted clients and a fresh isolated restore remain acceptance gates.
