# Company source-job image resolution

At 10:20 UTC on 27 October, the normal backfill timer started successfully but
its nested recovery-gate invocation failed before a provider request. The journal
retained the exact Docker command: two different 64-character image IDs had been
joined by a newline and passed as one quoted image argument. Docker rejected it
with `invalid reference format`; the wrapper then described the result as a closed
offsite recovery gate and exited successfully. The persisted recovery gate was
open, CR requests were below the existing daily cap, and two weekly pairs remained
pending. This was an invocation failure, not evidence of a failed recovery.

`docker compose images -q backend` is not a unique serving-runtime selector when
multiple service-associated containers/images are visible. A normal one-off probe
did not reproduce the incident; the recorded command, rather than that probe,
establishes the multi-image argument. No provider request or production data change
was made by the diagnostic probes.

The shared stdlib resolver queries the single running, non-one-off
`curated/backend` container and inspects its immutable image ID. It checks runtime
identity, labels, running state and image format, and refuses missing or ambiguous
service selection. It emits only the image ID; inspected runtime environments and
Docker stderr are never echoed. All five company source/recovery/health wrappers
use the same resolver. A closed recovery gate still defers growth; Docker execution
errors propagate separately so a failed invocation is visible.

Tests exercise filtered service selection, missing/ambiguous/stopped/mismatched
runtime data, multiline or mutable image references, credential redaction, existing
overlap/backup behavior and gate-versus-runtime exit codes. Read-only execution on
the real host returned the immutable image of the existing serving backend.

Deployment must use a new immutable helper directory, preserve live compose/env
configuration and all timers, wait for the existing maintenance lock, and keep the
serving backend unchanged. Only the missing bounded backfill is then run through
the existing recovery, capacity and source-budget gates. Public publication remains
subject to its normal once-per-UTC-date policy. Actual adoption and catch-up proof
will be recorded separately; they are not inferred from these source checks.
