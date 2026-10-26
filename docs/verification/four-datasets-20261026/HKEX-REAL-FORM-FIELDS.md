# Real Form 3B missing-field semantics

A bounded counted technical read of actual notice DB20261026E00008 established
that the form identifies listed issuer stock code 02536 while naming an associated
corporation and its Ordinary shares without an associated stock code. The listed
issuer share class is not supplied by this associated-interest form. Substituting
02536 for the associated security or joining the company by name would be false.

The normalized security contract now preserves null stock codes/classes. Additive
migration 008 removes only the two NOT NULL constraints; applied migration 004 is
unchanged. Existing known-code grammar, exact scoped source IDs, security conflicts,
policy gates, field limits, source isolation and recovery remain. The browser labels
unknown values explicitly. A real PostgreSQL regression covers distinct primary and
associated identities, repeated migration, physical dump/restore, publication and
SELECT-only reads without borrowing the primary stock code.

The source date-control qualification returned only two notices for relevant events
20-26 October, versus five summary observations in that publication period. This
is an event filter, not a complete filing-date inventory. No full filing window is
published by this contract correction; actual transport, parser, enumeration,
revision closure and declared-field coverage remain separate acceptance gates.
