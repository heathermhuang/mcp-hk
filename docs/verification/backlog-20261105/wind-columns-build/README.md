# HKO wind CSV columns — build evidence, 7 November 2026

The [official dictionary](https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/HKO_open_data_10min_wind_Documentation.pdf)
specifies five columns, a native twelve-digit calendar timestamp, provisional data,
and ten-minute updates. Direction/speed/gust markers and the calm-speed space are
retained as source strings. No timezone, unique station inventory, geography or
current-observation qualification is inferred.

The three saved complete publisher responses each contain 30 five-column rows.
Retained earlier schemas also contain an unlabelled generated `_column_6`, absent
from the source header. That metadata caused otherwise matching current responses
to fail drift checks. Only that exact historical generated overflow is excluded
from comparison when accepting the dictionary-backed current five-column contract.
Source-declared fields, changed headers/types, invalid dates/markers, current extra
columns and empty/error bodies remain held. Current values are never dropped or
rewritten. The old overflow's contents remain unknown; no meaning is invented.

A new contract-specific variant key prevents an older valid cache from bypassing
revalidation and retains legacy variant metadata separately. The source cache
target is 600 seconds according to the published update interval; this does not
prove observation freshness. Validation is offloaded because it can iterate rows.
The normal row/field/cache/variant/source/recovery bounds remain unchanged.

Full saved-body replay matched actual local HTTP/native MCP for all three original
resources, with 30 raw rows each, three fixture reads and zero provider requests.
All nine imported legacy variant metadata rows remained byte-for-byte unchanged.
Historic overflow values were not recovered. This is build/fixture evidence, not
current hosted availability, language equivalence or semantic acceptance.

Tests cover native marker/value preservation, bounded cache/revalidation keys,
legacy metadata retention, future overflow/named-field drift, malformed dates and
nonfinite/missing values. Hosted verification and fresh isolated recovery remain
pending. The public Hydro reuse hold remains in place.
