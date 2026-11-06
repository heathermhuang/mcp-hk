# Notification detail — build proof, 7 November 2026

The original `1a4d8dd19c1d4469bac87ab932e682f4` resource is an explicit native-ID
detail request. Its generic parameter binding already works. A single request for
an ID from the preserved published list returned HTTP 200 with a complete fixed
`NotiDetail(...)` response; the ordinary JSON parser rejects that wrapper.

The [publisher specification](https://www.gov.hk/en/about/govdirectory/mobileapps/psi/iamsmart_newsandalerts/datasets/iAMSmartNews%26AlertsDataSpec.pdf)
connects this detail request to original IDs in the notification list. Page two was
visually checked. The exact dataset/URL/JSON profile now unwraps only the complete
fixed callback without executing JavaScript, validates its known native field
layout and requires the response ID to match the requested ID. Malformed JSON,
changed fields/types, errors, arbitrary callbacks, trailing scripts and workbook/
map/nested selectors remain held. Original version hashes use source bytes.

All three multilingual message fields remain raw strings. Embedded text, images,
HTML or links are neither rendered nor fetched. The list/detail dictionary sections
name different timestamp units; native integers remain unconverted and their units
unqualified. No active-alert, observation-freshness, safety or complete-feed claim
is granted. Language equivalence, current source availability and service status
are not inferred from one body.

The captured body replays through local HTTP/native MCP as one original record
with ten fields. The existing list replays ten notices with matching clients. Both
use two fixture reads and zero provider requests; metadata requires the original
hyphenated parameter name. Focused tests start with the pre-existing unsupported
adapter state and cover identity binding, raw values, malformed/error framing,
selectors and exact-profile isolation. The source pilot, dictionary hashes and
client results are in the adjacent receipts; no original notice prose is committed.

The single live pilot overlapped the two running qualification lanes. That was an
operator sequencing error; subsequent work used the saved body, and a lane must be
paused before any further live pilot. No source/HTTP identity, quota, retry rule,
record/row/cache bound or production permission was changed.

Exact-head CI, coordinated deployment, actual hosted HTTP/native MCP checks and a
fresh accepted backup/isolated restore remain pending. Hydro reuse, wider frozen
graphs, source/capacity holds and the complete programme remain open.
