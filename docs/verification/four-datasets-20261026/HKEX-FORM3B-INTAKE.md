# Bounded Form 3B document intake

This implements actual HTML document parsing and a fixed-route transport for the
inspected English Form 3B structure. It is **not** a released full-filing feed or a
qualified complete filing window. No production policy, cohort, credential or
schedule is activated by this change.

The document context contains the exact notice serial, published search reference,
stock code and issuer context. Search references are not claimed as permanent
issuer IDs. The adapter accepts only the fixed `NSForm3B.aspx` route and approved
context keys, with no redirects, authentication reuse or request retry. The source
collector commits its durable reservation before HTTP dispatch. Unsupported context
fails before reservation. The actual response-body hash and resolved source URL are
retained; normalization follows capture, and a rejected document stays rejected.
The source's raw-byte retention mode still decides whether HTML may be stored.

The parser preserves source event, awareness and filing dates separately; unknown
dates stay unknown and are not derived from serials. The listed issuer and the
associated security remain distinct. An undisclosed associated stock code or listed
share class is null. Issued shares belong to the associated security. Aggregate
before/after rows retain missing capacity codes. Capacity rows, spouse rows and
controlled-corporation rows remain separate and are never summed into an asserted
ultimate holding. One event holds its distinct highest/average price measures,
currency and per-share units without rounding or duplicating its share quantity.

Parties and control relationships are filing-scoped. Unique exact names explicitly
declared in that filing's control table can link its own rows; ambiguous names do
not resolve to an existing corporation reference. No cross-filing/name-based global
identity is created. Control percentages are distinct from ownership percentages.

Contacts, addresses, commercial name codes, signatures and supplementary narratives
are not selected for normalized facts. Nonempty child, derivative, joint, trust,
noncash-consideration or unqualified consideration-unit fields fail closed. New
event panels and ambiguous position amounts also fail rather than disappear.

Additive migration 009 preserves applied migrations and adds the required source
columns and control table. Real PostgreSQL tests cover repeated migration, source
isolation, source reservations, rejected captures, physical backup/restore and
SELECT-only serving of all typed facts across all 16 source tables. Source-shaped
tests use invented notices, not captured HKEX records. Eight rendered fixture
journeys passed in English and Traditional Chinese at 320/390/768/1280px, including
separate price labels, control relationships, unknowns, overflow and clearing data
when browser mode becomes unavailable.

Actual candidate-format qualification remains pending. On 27 October HKT, the
existing budget-writer host accepted TCP then closed SSH before authentication.
Its authenticated HKEX daily reader continued to return the accepted daily version.
No provider request was dispatched by this candidate because the required durable
source-budget admission could not be established. The failure is an operator-host
access dependency, not a qualified HKEX denial or a successful live parser check.

Next: qualify a counted actual response with this exact transform; finish actual
listing/inventory and pagination reconciliation, source-appropriate completeness
proof, revision closure and independently restored publication. The existing
framework's independent detail-hash inventory gate is not fabricated or bypassed.
The inspected seven-day source date filter remains event-based; it does not prove
complete filing-date coverage. Other form families and public output modes require
their own source qualification. The four-dataset programme remains incomplete.
