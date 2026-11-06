# HKO cyclone list — build evidence, 7 November 2026

The [publisher dictionary](https://www.weather.gov.hk/wxinfo/currwx/HKO_TCTrackInfo_DataDictionary_en.pdf)
explicitly defines absent `TropicalCyclone` entries under `TropicalCycloneList`
when HKO issues no forecast track. Its page-two summary and footnote were visually
reviewed. The saved exact empty list is therefore distinguishable from a source
failure. This describes this issuer's feed contents, without a worldwide cyclone
inventory or safety/current-observation claim.

The exact original XML list now validates its root, children and four declared text
elements. Native IDs, names and published URLs remain unchanged; URLs are not
followed or guessed. Error text/attributes, unknown fields, missing/duplicate tags,
malformed IDs/URLs and unsupported selectors stay held. An empty response carries
publisher-declared field types with zero observed values and zero records. No
observations are invented. Empty/nonempty transitions retain one record schema.
The new variant key preserves legacy metadata separately. A five-minute source
validation cache is an operational target, not an HKO availability/update promise.

The exact captured body replays through local HTTP/native MCP with zero rows and
four declared fields, one fixture read and zero provider requests. Both imported
legacy variant metadata rows remained unchanged. Thirteen focused tests cover
empty/nonempty transitions, malformed/error responses, selector isolation, native
IDs and legacy compatibility. Hosted acceptance and fresh isolated recovery remain
pending. The separate GML empty-track placeholder remains unverified; its spatial
specification supplies no matching empty-state rule. Hydro reuse remains held.
