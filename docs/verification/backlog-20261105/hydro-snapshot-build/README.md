# Hydro published map snapshot — build evidence, 6 November 2026

The exact inspected resource `35f4fa534d677141e2d81d8c15b34287` is labelled CSV but
returns a download interface at `https://current.hydro.gov.hk/main/download.php?lang=tc`.
Its published first-party client `https://current.hydro.gov.hk/_js/data_download.js`
requests a pre-download map snapshot from `/data/static_geojson.php` with `time`
in `YYYYMMDDHHmmss` and mode `A`. The client rounds to a quarter hour. The separate
CSV download uses selected points/dates or an all-points monthly archive; those
period-download contracts are not implemented by this change.

Both remaining original language pages were independently retrieved and publish the
same first-party client. Bind only these three exact inspected original interfaces. Require explicit timestamp and
mode, validate the calendar/quarter hour, and accept only the observed mode A.
Require complete FeatureCollection framing and original prediction properties;
reject error wrappers, mixed or wrong timestamps, invalid selectors and unsupported
modes. Preserve raw feature geometries, IDs and string values. The original body
hash is distinct from the existing CSV-reader version namespace. Existing source,
row, field, cache and variant bounds remain unchanged.

One explicitly selected `time=20261106000000&mode=A` request returned 1,158 original
features, all carrying the selected time/mode. These are source prediction features,
not unique facilities, observations, a complete point inventory, period CSV
coverage or geographic qualification. The publisher says not to use the product for
navigation. Native timezone semantics and original-representation equivalence remain
unreviewed. No new geographic binding, source inventory entry or service is added.
Original period-file/language equivalence remains unreviewed; this binds only the
shared published map request, without counting distinct dataset gains.

The saved complete response replays through local HTTP/native MCP with 1,158 rows,
three fixture reads and zero provider requests. A local replay helper initially matched
the original HTML URL instead of its bound snapshot URL; its failed isolated state
was retained and exact fixture routing corrected. No reader or production change
was needed for that harness failure.

Focused reader checks cover all three interfaces and malformed/wrong-time responses.
The mandatory full push-hook and exact-head CI remain gates. Hosted acceptance and fresh recovery are
pending. Source metadata and fixture evidence do not establish current production
availability or navigational/semantic readiness.
