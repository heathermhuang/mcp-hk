# Publisher serialization readers — build proof, 6 November 2026

A bounded investigation retrieved one exact original resource URL per remaining
host/format parse-failure group. Nine original responses were inspected under the
existing DNS-pinned fetch, source pacing and native maintenance gates. The ARC
process paused after a saved response and resumed as the same validated process.
This sampling does not qualify every resource in a group.

Three source representations have complete, unambiguous framing:

| Exact captured resource | Observed representation | Dated parser replay |
|---|---|---|
| `1e6a30329eb17f70afdd8ba409cbd051` | UTF-8 BOM CSV served at a Fire Services XLSX URL | 25 original rows |
| `1cefa98483583d4ab9235f8764187d5f` | Audit Commission top-level JSON objects emitted sequentially | 516 original objects |
| `4c2d28574d52c5fc4804943be6c76e78` | Fixed `NotiList(...)` JSONP response | 10 original notices |

Readers apply only to explicit source URLs: twelve frozen Fire Services filenames,
four Audit Commission filenames, and the exact notification URL. Flat CSV requires
complete multi-column records and rejects workbook/map selectors. Actual ZIP
workbooks retain their ordinary reader. JSON sequences require complete strict
objects with no ignored suffix; malformed arrays are never repaired. The fixed
JSONP wrapper is stripped without executing JavaScript, and its complete payload
uses the ordinary strict JSON reader. Duplicate keys and nonfinite values remain
errors. Existing response, row, field and source budgets remain unchanged.

All three original captures passed local HTTP/native MCP replay with zero provider
requests and exactly three fixture reads. Version hashes remain the hashes of the
original source bytes, not a reconstructed JSON document. Schema records the
advertised format, observed framing and full byte consumption. Leading zeroes,
original names/values and notice schedule/expiry fields remain raw; notices are
not claimed active. This proves dated source replay, not fresh hosted acceptance
or equivalence between languages, files, periods or entities.

Captured source SHA-256 values:

- Fire Services: `212b9595b388bef8c6591daec9348d4874a83b6b02aa9a0acd4a2574dca6f54d`
- Audit Commission: `72f9c978f5df8eec2c737a47a3141f29bb5dcb79ff193045ae6a9d14fce6e840`
- Notifications: `1264b92b06c112bf9eae03cafe1a6975a0a2022e018e84a11ce098a9398d30ce`

The other inspected originals retain explicit unresolved reasons: an AccessGuide
HTML response, a Census XML-labelled HTML page, a Town Planning GML-labelled HTML
page, malformed Architectural Services JSON arrays, an incomplete CNSD JSON object,
and malformed TID XML. A representative response does not establish every other
resource's body or availability. No alternate host/header/proxy or guessed source
repair was used. The full frozen programme and these individual investigations
remain open.

Tests exercise complete framing and source hashes, selectors, real-workbook
compatibility, unrelated URLs, arbitrary callbacks/trailing scripts, duplicate keys,
nonfinite values, malformed arrays and the existing row ceiling. Required checks,
exact-head CI, actual hosted queries for every candidate, coordinated deployment
and fresh isolated recovery remain release gates. No new semantic binding is added.
