# Live public transport arrivals

## Bus stops and direct journeys

Transport and the shared catalogue/resource interface appear in `hk_data_packs`
and connected catalogue search. Other transport feeds still use the resource
workflow below; absence of a dedicated tool never proves a source is absent.

- `hk_transport_stop_search(q="Lan Kwai Fong")` matches partial English or Chinese
  bus stop names without case sensitivity. Optional `lat`, `lon`, `radiusM`
  search nearby WGS84 locations; distances are straight-line, not walking routes.
- `hk_transport_stop_routes(stopId="261")` returns directional route memberships
  and original regular/special-service and pickup/dropoff flags.
- `hk_transport_journey(origin="Lan Kwai Fong", destination="Seymour Road")`
  finds direct bus routes and independently attaches verified Citybus, KMB/LWB
  and NLB live ETAs.
  Names, exact returned TD stop IDs, or `originLat`/`originLon` and
  `destinationLat`/`destinationLon` are accepted. Use ALS address search first for
  arbitrary landmarks; choose ambiguous addresses rather than guessing.

HTTP equivalents are `GET /api/v1/transport/stops`,
`GET /api/v1/transport/stops/{stopId}/routes`, and
`POST /api/v1/transport/journeys` with the same argument names. `operator="CTB"`
restricts discovery to Citybus; an empty operator searches all indexed buses.
`includeArrivals=false` requests reference routes without operator reads.

The index joins official bilingual GTFS `stops.txt` files with full
`ROUTE_BUS.xml` and `RSTOP_BUS.xml` files. The similarly named CSV route/fare
files are **delta changes**, not full stop inventories. Output preserves source
URLs, hashes, retrieval times and source update dates. No route, stop, location or
ETA is seeded. Complete validated generations publish atomically in the existing
SQLite store and are included in its backup. This optional index does not change
accepted-pack readiness.

Refresh is on demand, once daily after success, with at most six refresh batches
per UTC day and a five-minute failure cooldown. A batch reads four fixed public
files with byte/row limits. Failed refreshes retain the last accepted index with
a stale warning. Unknown pickup/dropoff code `0` is retained but never permits
boarding or alighting. Provider clocks and live arrival freshness are independent.

TD stop IDs are **not** Citybus IDs. Live joins check the current Citybus route,
direction and operator stop name/location against selected TD stops. Sequence
numbers are lookup hints only; actual operator order determines live queries and
stop counts. Changed identity, source errors or request bounds leave a reference
candidate with an explicit `arrivalStatus`/`arrivalError`, never a successful empty
ETA. Each journey has at most 64 operator-resource lookups in a shared 45-second
window; the persisted daily budget is 5,000, including cache hits.

Joined ETAs support Citybus, KMB/LWB and NLB. Other buses have reference route discovery
and separate generic arrival resources. Rail, ferries, transfers, service-day
calendars, diversions, walking times and fastest-trip ranking are not inferred.
A dated route alone does not establish current operation.

KMB service types come from the published route list; no service type is assumed.
Current KMB stop names append a pole code such as `(WT916)`. The reviewed name
binding removes only an identical final `(AA999)` annotation in both English and
Traditional Chinese before exact comparison. This is an explicit inference from
nine official stop records, not a whole-network identity crosswalk. Full original
names remain in the operator detail, and the 35 m location/current-order/occurrence
checks remain mandatory. Unmatched names or more distant TD points stay unknown.
Its ETA can include predictions in other service types sharing the stop, so source
variant warnings remain visible and the result never counts independently identified
buses. KMB's case-sensitive stop IDs retain all 16 characters. NLB route IDs select
their own ordered stop arrays, independently of the TD direction label. Verified
reverse order is `ineligible`, separately counted as `verifiedNotServingOrder`;
missing identities, unknown service calendars and source failures remain unknown.
NLB ETA does not identify repeated boarding visits, which stay unverified. Native
`estimatedArrivalTime`, `departed`, `noGPS`, route variants and stop flags remain raw.

`totalMatched` retains its original TD-reference count, also exposed as
`referenceCandidateCount`; `expandedCandidateCount` and `coverage.candidate` count their
expanded operator variants, including unknown references whose expansion failed.
Namespace/service-type/route-ID boundaries prevent cross-operator merging. The
same 64 lookups, 45-second comparison, daily budget, freshness and presentation
limits apply. A partial result is earliest among checked candidates, not the network.

Rehearse real HTTP/MCP source reads without changing production:

```sh
PYTHONPATH=src .venv/bin/python scripts/verify_transport_search.py --local \
  --out /tmp/mcp-hk-bus-rehearsal.json
```

After release omit `--local` to test the actual public endpoints.

## Other operator arrival resources

Transport feeds use the existing `hk_catalogue_search` → `hk_dataset_resources` →
`hk_resource_schema` → `hk_resource_query` workflow. HTTP uses the same service.
A catalogue entry is not evidence that every route, stop or operator works.

## Supported request contracts

| Operator | Arrival resource ID | Source parameters |
|---|---|---|
| MTR trains | `4b51588763e1b021e5252500f88e5833` | `line`, `sta`; optional `lang=en` or `tc` |
| MTR Light Rail | `32de1cc093c94945abccd4f4f5da0b78` | `station_id` |
| MTR Bus / feeder buses | `91a85d4046b496b9c5a1116ab2653a81` | `routeName`; optional `language=en` or `zh` |
| KMB / Long Win | `284a055c48fd543d67208377727e7226` | `route`, `service_type` (route-wide ETA); stop ETA resources are also supported |
| Citybus | `2b1b8d6b425bf3ddd1e1ddb811d54ba4` | `stop_id`, `route` |
| New Lantao Bus | `6364bb25c65c4f24f73b9b9a982c05a3` | `routeId`, `stopId`, `languageCode` |
| Green minibuses | `b9361a1598c2265a3992a54e4cabdf35` | `route_id`, `route_seq`, `stop_seq`; stop-wide ETA is also supported |
| Sun Ferry | `479f49ec6b78e5a94e4d176227488d95` | `routecode`, e.g. `CECC` (Central → Cheung Chau) |
| Hong Kong & Kowloon Ferry | `340cd0efe47f2162049e823b3beb9d77` | `route_id`, `direction` (`inbound` or `outbound`) |
| Fortune Ferry | `e34a14f5c386e36b39bdbcadfa1dda15` | `route_code`, e.g. `NPKT`; published endpoint currently returns 404 (checked 2026-10-17) |
| Water Taxi | `6b9abfae6619ecbd96c06b48a8a1bcdf` | `route_code=WATERTAXI`; published endpoint currently returns 404 (checked 2026-10-17) |

The Citybus adapter uses the current v2 endpoints even when catalogue metadata
still contains the retired v1 address. MTR train queries add the required line and
station. MTR Bus uses the operator's documented read-only JSON POST. HKKF supplies
the route/direction missing from its catalogue URL. Original catalogue/source URLs
are retained beside the resolved request URL in provenance.

```json
{
  "tool": "hk_resource_query",
  "arguments": {
    "resourceId": "4b51588763e1b021e5252500f88e5833",
    "parameters": {"line": "TWL", "sta": "CEN"},
    "requireFresh": true,
    "limit": 20
  }
}
```

HTTP equivalent: `POST /api/v1/resources/4b51588763e1b021e5252500f88e5833/query`
with `{"parameters":{"line":"TWL","sta":"CEN"},"requireFresh":true}`.
Call the schema operation without parameters to discover required settings.

## Freshness and semantics

- Train/Light Rail responses are cached for at most **10 seconds**. Other arrival
  responses use **20 seconds**. `requireFresh=true` bypasses an arrival cache.
- The source timestamp must be at most 60 seconds old for train/Light Rail and
  150 seconds old for the other arrival feeds, with at most 30 seconds of future
  clock skew. This is independent of the time our service fetched the response.
- Expired or semantically invalid arrival responses fail closed. They never fall
  back to a previous successful arrival list, even without `requireFresh`.
- Fresh empty arrival lists say `arrivalState=no_arrivals`; provider errors do not
  become successful zero results. NLB empty lists require a fresh provider HTTP
  Date because that response has no per-arrival generation timestamp.
- Individual KMB/Citybus/ferry records with expired data timestamps are omitted
  with `omittedStaleRecords`; an entirely expired list fails. Source flags and
  remarks distinguishing scheduled departures, GPS predictions, suspensions and
  advisories are preserved. MTR Bus's testing/service advisory is exposed as a
  warning instead of silently treating scheduled times as GPS predictions.
- MTR train/platform/stop wrappers are flattened into records with the original
  source fields and the station/platform/stop identity. No estimated times are
  invented from placeholder fields. Ferry time-only strings retain source format.
- `schema.transport` exposes cache TTL, source timestamp/age, freshness deadline,
  operation, advisory and validation scope. Query/coverage HTTP responses use
  `Cache-Control: no-store` so downstream caches do not extend these windows.

## Honest coverage

Changing the transport policy invalidates old generic-reader success receipts,
including MTR error JSON previously counted as queryable. Missing settings appear
as `needs_selection`; errors remain failures. A successful receipt expires to
`stale` after the response-cache interval and is updated by the next source read.
`/api/v1/coverage.realtimeTransport` reports these states per operator. They apply
only to the last tested selections, not the whole network. The explorer labels
arrival feeds separately from static routes/stops, and shows required settings.

This does not claim live red-minibus coverage or an ETA feed for ferry operators
that only publish timetables. Provider downtime/access restrictions remain visible.
Schema/parameter discovery does not erase a previous upstream failure receipt.

### Fortune Ferry and Water Taxi source investigation (2026-10-17)

Both DATA.GOV.HK entries still publish
`https://www.hongkongwatertaxi.com.hk/eta/?route={route_code}` and the same old
[API dictionary](https://www.hongkongwatertaxi.com.hk/csv/Watertaxi_FortuneFerry_ETA_API_Specification_and_Data_Dictionary.pdf).
Direct HTTP and real-browser requests for `NPKT` and `WATERTAXI` return the
operator's HTML 404/maintenance page. The dictionary itself also returns 404.
Some non-browser clients receive a Cloudflare 403 first; neither is a live feed.

The current [Fortune route page](https://www.fortuneferry.com.hk/zh/route-and-fare)
and [Water Taxi government routes](https://www.hongkongwatertaxi.com.hk/Schedule-And-Ticket/Government-Public-Routes/)
publish schedules, with no working replacement ETA endpoint found in their public
pages/scripts. Fortune's same-path `/eta/` URL returns 502. The current
[`hk-bus-eta` Fortune implementation](https://github.com/hkbus/hk-bus-eta/blob/master/src/fortuneferry.ts)
also disables the old API and returns explicitly scheduled departures instead.
Those schedules are not substituted for live arrivals in mcp.hk.

The two operators have separate coverage labels and documented example parameters.
404 is recorded as `SOURCE_NOT_FOUND`, not a successful empty arrival list. A
replacement endpoint must return real source timestamps and pass the freshness
checks above before either feed can be counted as working. Upstream restoration
or an operator-published replacement is still required; do not mark these repaired
merely because the local adapter or availability checks pass.

## Verification and recovery

Run deterministic regressions with `pytest tests/test_transport.py`. Run the
bounded live HTTP and MCP matrix after a deployment:

```sh
python scripts/verify_transport.py --base-url https://mcp.hk --mcp \
  --out /tmp/mcp-transport-live.json
```

Use `--only Citybus,HKKF` to resume only affected cases after investigating a failure.
The matrix includes two MTR lines, Light Rail, MTR Bus, KMB, LWB, Citybus, NLB,
green minibuses, Sun Ferry, HKKF, Fortune Ferry and Water Taxi. It probes HTTP and
MCP independently even when the first protocol fails, and exits nonzero for an
unavailable source. Use `--only Fortune-Ferry,Water-Taxi` for these two feeds.
Empty live responses are recorded separately
from nonempty arrivals. Each receipt includes source time, source age and TTL.

On a failure, inspect its code and the operator's published service state before
retrying. A stale timestamp, provider error or changed field contract cannot
advance a success receipt. Release rollback uses the prior verified Worker/image
and the accepted R2 checkpoint; no catalogue re-import is required. Test restore
and republish the dated overview after releasing the new validation policy.


The unavailable Fortune/Water Taxi ETA profiles expose a clearly labelled published
timetable alternative. Water Taxi additionally links the accepted Transport
Department resource `2c3ad746961a833f59740f4abbf26644`, readable through the ordinary
resource query API. Its departures are schedules, never live ETA predictions.
The broken operator ETA endpoints remain unavailable until a successful real-source
read qualifies a restored or officially replaced endpoint.


## Hosted Citybus source transport

The existing authenticated Worker source relay carries the three already supported
Citybus V2 selections: route stops (`route`, `direction`), stop detail (`stop_id`)
and ETA (`stop_id`, `route`). A shared shipped manifest fixes resource IDs, HTTPS
host/path templates and parameter bounds in Python and Worker code. It accepts no
caller-selected destination, body, extra/repeated parameter or credential.

This closes a hosting-path gap: the existing fixed Citybus route-list relay was
readable while the direct container route-stop request returned source HTTP 403.
The provider's public V2 format is unchanged. It does not add a provider, key,
semantic join, quota, container or new routing service. Public clients still use
the normal typed HTTP/MCP tools. Source URLs/provenance remain Citybus's originals;
`schema.sourceTransport` identifies `approved-worker-relay`.

ETA reads omit conditional validators and send `Cache-Control: no-cache` to the
source. The existing provider timestamp/expiry checks and maximum 20-second cache
remain mandatory. A denial, rate limit or redirect never selects a different
source path or stale ETA. Unknown identity/order and empty/expired predictions
retain their original caveats. Production recovery/adoption and successful live
predictions must be verified before closing the earlier Citybus hold.

Official request contract: [Citybus API specification V2.01](https://www.citybus.com.hk/datagovhk/bus_eta_api_specifications.pdf).
Provider maintainer: [DATA.GOV.HK Citybus dataset](https://data.gov.hk/en-data/dataset/ctb-eta-transport-realtime-eta).
