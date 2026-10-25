# Fresh implementation review

Reviewed the actual SFC branch against the copied reviewed plan and the installed
review checklist: policy/mode bypass, exact CE and entity/regime/type, temporal
semantics, source-request admission, uncertain failures, transaction ordering,
reader/writer privileges, output/privacy, restoration and existing-pack regression.
The review uses direct code inspection and negative reproductions; it is not
independent source permission or live SFC acceptance.

## Findings corrected

- P1: staging accepted normalized bytes larger than the request's persisted byte
  reservation. It now checks the exact payload length against the settled attempt;
  exceeding the reservation rolls back the complete candidate. Regression reproduced
  with a one-byte reservation and a larger valid corporate record.
- P1: restore qualification accepted a caller-asserted artifact checksum. It now
  hashes the actual local retrieved artifact, rejects symlinks/hash mismatch, rejects
  the same database identity, and compares every row of all ten SFC source tables.
  Tests reject an altered restored fact and check every synthetic fact/capture/control.
- P2: publication trusted a previously recorded fact hash after owner-side changes.
  It now recomputes all candidate facts under the publication transaction, in addition
  to the restore proof, policy and expected-old-pointer checks.
- P2: an input checksum called raw_sha256 could imply that the normalized offline
  bytes were official register-page bytes. It is now explicitly
  normalized_payload_sha256 and the manifest says normalised-offline-v1.
- P2: a session-only request could be used as the capture for a corporate detail.
  Staging now accepts only a settled detail/retry attempt with matching run and CE.
- P2: private invalid-CE errors used the generic 503 mapping. They now return 400,
  with authentication and gate checks exercised without a configured database.

The new status-only MCP tool intentionally changes the base tool inventory from
28 to 29. The two exact inventory expectations were updated with explicit assertions
for hk_sfc_status; no tool-preservation or parity assertion was removed.

## Result and limits

No blocking findings remain **for the disabled engineering contract**. Production
cannot fetch SFC records: there is no live HTTP transport, no source timer, no
activation environment flag or public purpose bypass. The pinned production policy
records unknown modes. Only capability status is discoverable; data routes return
explicit errors, and the bilingual exact-CE form is disabled with no download link.
The base health and all existing company contracts remain independent.

The offline model, state and SELECT-only reader are exercised with fabricated input
and an explicitly synthetic policy. They are not a qualified parser of an official
service response. Exact official route/session parsing, raw-source lineage, a real
tracked-purpose cohort, independent field reconciliation, allowed-mode public
readers/exports, retention/deletion automation and ordinary offsite recovery require
an actual source qualification decision. Those are activation blockers, not passed
review items. No unqualified mode is advertised as a working live dataset.
