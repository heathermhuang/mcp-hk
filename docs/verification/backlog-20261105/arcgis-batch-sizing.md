# Demonstrated ArcGIS request-cost repair

The actual adopted-release batch reproduced SOURCE_TIMEOUT at the unchanged
120-second complete-read deadline for planning-application resource
`d0d031bf88e843e97855e31576402825`, layer 2, and Slopes resource
`35119286a04b53cf9efb9d33e4d5b2e1`, layer 0. Other planning selections independently
accepted 1,324 historical-amendment, 16 current-amendment and 2,179 current-application
source rows. These native counts are selected views, not deduplicated applications.

The repair uses the provider's declared maxRecordCount, capped at 500 records and
a conservative 2,000-character URL. Missing/invalid declarations retain 100. Only
actual size/transfer-limit responses shrink a batch; provider denials are not
retried. Every accepted page still contains exactly the requested native integer
OID set, and the final complete ID set must match the initial set including its
cardinality/types. The existing one-million-ID, 128 MB representation, two slots
and 120-second deadline remain; the final reconciliation call shares that deadline.

Regressions prove fewer requests under an authoritative provider limit and long
IDs, bounded URL/body adaptation, transfer-limit rejection, wrong/boolean IDs,
changed/duplicate final IDs, and immediate stop on a provider denial. Local fixture
success is not source/runtime qualification: exact-head CI, actual adopted-source
rechecks and fresh accepted backup/isolated restore remain required for this repair.
