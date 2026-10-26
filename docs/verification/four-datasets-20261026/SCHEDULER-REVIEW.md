# Ordinary scheduler findings and repair

26 October 2026. These findings came from actual scheduled occurrences, not an
operator substitute. The company source timer fired at 05:00:17 UTC; collection,
publication and local backup succeeded, and the unit exited at 05:03:41. The
accepted company version advanced to `official-731745eb39cd14f3f986ac01521f0525`.

The 05:17 company offsite unit failed at 05:21:19. Its consistency guard correctly
rejected a changed database checkpoint before uploader dispatch. Comparing producer
fingerprints shows only `official_source_state` changed; all 900 raw captures were
stable. The independently scheduled 05:20 health verifier wrote its cached summary
to that table while the backup held the shared maintenance lock. The verifier did
not previously join that coordination protocol. The failed daily job
`c65eb6439d0b1fce35b5feacc011587b` and its artifacts remain retained.

The existing maintenance owner independently landed the lock repair in PR 96.
This change preserves that implementation and its real-lock regression. Health
takes the nonblocking maintenance lock. An owning backup/collector
causes a host-only deferral receipt and the existing follow-up marker, with no
database access or write. A bounded comparison also lets the existing 06:00 check
notice recovery evidence changed after an earlier failure. The cache remains
honest until verification runs. No timer is added and no snapshot fingerprint or
failure is ignored to manufacture qualification.

HKEX's actual 05:20 timer/unit completed successfully at 05:20:57, including its
source-specific candidate/accepted recovery path. The accepted snapshot became
`hkex-daily-41689de8d0feb159d3ced7fa3a6ec356`, with the same 1,004 facts and
23 October summary cutoff. Its internal run incorrectly records `manual` and a
fractional current timestamp. The wrapper read systemd's formatted timespan and
tested `isdigit()`. It now reads typed `busctl` microseconds and pins the latest
configured occurrence (01:20/05:20/09:20/10:20/14:20 UTC). Operator starts remain
manual; canonical timer keys prevent duplicate occurrence collection. The original
incorrect receipt is preserved, and the next actual timer is needed to verify the
corrected internal provenance.

Meaningful regressions cover a busy backup lock causing zero health database
dispatch, deferred follow-up, read-only recovery-checkpoint comparison, typed versus
formatted timer values, stale/future triggers and prior-day catch-up boundaries.
Focused correctness/operational review: no blocking findings in this repair scope.
Full exact-head checks/CI, actual adoption and future ordinary-operation proof are
separate gates. A subsequent manual backup qualification cannot establish daily RPO.
