# Live public transport arrivals

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
