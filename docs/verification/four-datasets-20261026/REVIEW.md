# Registry outcomes and address queue review

26 October 2026. Scope: first source-scoped repair in the four-family programme.
This is not acceptance of the whole programme or of production deployment.

Root cause reproduced before the fix: the collector rejected all HTTP 400s before
reading their bodies; nine negative-response/lineage cases failed. Narrow response
recognition and bounded receipts now pass those cases. Generic 400, malformed/HTML,
extra-field and access-denial responses remain failures. Exact string BRNs retain
leading zeros. No negative response deletes a fact or establishes dissolution.

Queue review found that never-attempted `-infinity` rows could indefinitely precede
due refreshes. Persisted weighted turns now separate priority, successful refresh,
first observation and unsuccessful retry cohorts, borrowing empty slots. A turn
and unknown address admission commit before network dispatch. Existing request and
byte reservations, source holds, writer ownership and quotas remain enforced.

The additive migration leaves migration 001 and accepted address/version membership
unchanged. Reader expansion tolerates deployment before migration 007. SELECT-only
credentials are sufficient; the explicit tracking CLI requires the existing owner
and ordinary writer lock. It accepts only exact already-eligible company identities.

Meaningful database contracts cover fake-clock due selection, cross-batch fairness,
prior-fact preservation on no-match/interruption, crash admission, physical dump
restore, schema identity and publication isolation. A test initially demanded that
a newly due priority row be first regardless of the persisted turn. The corrected
contract requires its bounded turn within the schedule, and excludes it before due.
The other initial failure came from omitting the required test-container environment;
the physical restore passed with that identity supplied. Neither failure justified
relaxing a production timeout or quota.

Focused correctness/security/data-semantics review: no blocking findings in this
candidate. Production adoption, live source examples and ordinary scheduled evidence
remain separate acceptance items. Old generic 400 receipts remain unresolved until
their actual source response is observed; they are not retroactively relabelled.
