# Archive activation and backend startup correction

The original archive feature is merged in PR #81. The production source schema
now contains all 341,047 disclosures, 426,219 capacity rows and 345,355 event rows,
with dictionaries and original issue identities. Existing company tables/pointers,
proxy/database containers and maintenance runners were preserved.

The candidate dump was uploaded to the existing private offsite store, downloaded,
SHA256-verified and physically restored into an independent local database. Every
row of all seven database tables matched production before source-only atomic
publication; see `production-source-qualification.json`. This proof is distinct
from the gateway's SQLite backup. Public consumer activation is still pending.

The first new backend image exposed a startup regression: the package initializer
imported the public MCP server, whose conditional tool discovery constructed the
gateway SQLite store in the backend's unwritable `/app`. The private backend
restarted and returned 502. The previous immutable backend source was rebuilt and
restored; its private HTTP health returned 200/ready. The database/proxy stayed up.
The initially recorded prior image identifier was no longer available, so recovery
used its retained immutable source rather than assuming image retention.

The fix makes the package's legacy `mcp` export lazy. Offline and private-backend
imports no longer initialize a public gateway; explicit `from mcp_open_data_hk
import mcp` and the CLI remain supported. A clean-process regression fails before
the fix and passes after; the legacy export test also passes. CI additionally
builds the real non-root backend image and imports it with a read-only filesystem
and networking disabled. No writable-directory workaround is used.

Activation sets the persistent Worker archive flag and makes the actual archive
page indexable after backend/source verification. Fresh official HKEX collection
continues to use its independent existing gate. Final production HTTP/MCP/browser,
actual controller/container adoption, restored five schedules, and fresh gateway
and accepted-source offsite restore results must be recorded before completion.
