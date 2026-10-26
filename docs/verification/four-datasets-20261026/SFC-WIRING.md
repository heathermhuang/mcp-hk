# Persisted SFC observation serving

26 October 2026. This source-scoped change connects the existing collector/state
model to actual status and qualified reads. It does not activate a public source
policy, collect a new corporate record, or complete the archive/live acceptance.

Status now reads installed schema, active policy, actual attempts/run, accepted
pointer, independently qualified manifest, cohort count, retention and source hold.
Database failure remains unavailable rather than a static unqualified success.
Revocation and failed runs retain the accepted-version identity while closing
unqualified modes. Offline normalized fixtures cannot claim qualified live transport.

Public REST and MCP share the source-bound private reader, exact CE and version
checks. A real-register capture format and the same checksum-pinned operator policy
are required before public facts pass. Only qualified tools/routes enter discovery.
The browser enables its distinct official-observation controls from usable persisted
capabilities, preserves CE/version/source across sharing and language changes, and
shows source dates, unknown bounds, original status labels and retained prior data
on failure. Archive lookup remains independent. History/export are not advertised
as implemented by this wiring.

The private SELECT-only reader receives only the additional job-status columns it
needs, with no writer role membership. Backend and gateway can adopt a bounded
`MCP_HK_SFC_POLICY_JSON` plus independent `MCP_HK_SFC_POLICY_SHA256`; an existing
operator policy file remains supported on the private backend. Gateway bindings
`SFC_POLICY_JSON`/`SFC_POLICY_SHA256` forward only that reviewed policy. An enable
flag grants no rights, and writer/backup credentials never enter the gateway.

Operator commands now provide `install --reader-role`, `activate-policy --file
--sha256`, `status`, `collect`, `qualify-restore --version --artifact --sha256`,
`publish --version --expected-version` and `revoke-policy --sha256`. DSNs stay in
the existing private environment (`SFC_WRITER_DSN`, `SFC_READER_DSN` and
`SFC_RESTORED_DSN`); they are never command arguments. `NONE` is accepted only as
the explicit first-publication expected pointer. Publication and rollback preserve
the existing source policy, physical-restore and compare-and-swap gates.

Verification includes real PostgreSQL run/policy/adoption state, physical restore,
manifest-corruption rejection, revocation, source failure, last accepted pointer,
REST/MCP parity, CE/version mismatch and denied-mode tests. Eight rendered fixture
journeys cover EN/Traditional Chinese at 320/390/768/1280px, keyboard detail focus,
overflow, source/version sharing, language changes and denied/unavailable states.
No SFC provider request occurs in those browser tests.

Focused correctness/security/data-semantics review found and corrected missing
status-column grants, static gateway status, stale-policy capability exposure and
missing manifest/capture-format checks. No blocking findings remain for this
wiring scope. Actual production schema/adoption, scheduled collection, source-scoped
offsite recovery, accepted real cohort and public output qualification remain
separate pending acceptance rows. The existing private parser/restore receipt is
reused as its stated proof; it is not relabelled a public or 25-CE acceptance.
