# Observed historical-results archive redirect

Actual instrumented reads of the held 15 July 2026 Happy Valley results request
returned HTTP 302 with a 200-byte body. The second read preserved only routing
structure and the original Location hash. An offline reconstruction matched that
hash exactly to the same-provider public archive route, with the same meeting,
venue and language. No target request or extra provider read was needed for this
match. The read settled within the unchanged 200-request/64 MiB daily limit.

The checked diagnostic release `42e3b89847e83ff10eb74c294a1f1398f880cc5a`
was actually adopted. Its fresh accepted checkpoint
`974c347c22d9e674e04faa1a96e4d4b4b0185b161a027b081ca673a0cc143024`
was independently downloaded and restored. All 15 Racing tables were verified;
the old hold, both inspection records, all three published profile facts and all
14 accepted meetings survived. All five schedules were restored and read back,
and the owned release slot was released. The hold remains active at this checkpoint.
See [machine-readable evidence](racing-archive-redirect-qualification.json).

The archive-handling change admits only one HTTP 302 hop from the fixed results
route to its fixed archive counterpart, with identical query fields, values and
language. The redirect and target each reserve their own request and bytes. Unknown
routes, credentials, fragments, query additions, another redirect, denials and
unconfirmed requests retain holds. Redirect mappings persist as factual source
metadata with body/Location hashes, without retaining HTML.

The operator reconciliation requires both actual settled inspections and the exact
Location hash. It preserves the original conservative charge and original error,
records immutable evidence in both source state and durable admission, and changes
only that routing hold. It resumes the matching queue entry and entries whose only
error was the global source hold. Other failures stay held. An isolated replay of
the actual checkpoint resumed exactly one matching and 52 globally blocked entries;
all accepted data, profile tables and inspections remained unchanged.

Reconciliation issues no provider request and does not claim that target results
were obtained. Subsequent archive reads must parse, reconcile both languages and
survive actual offsite restore before publication. Full historical coverage and
the wider four-dataset programme remain incomplete.
