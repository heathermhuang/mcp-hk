# Hydro public reuse hold — 6 November 2026

The Marine Department's [endpoint notice](https://current.hydro.gov.hk/main/disclaimer.php?lang=tc)
permits noncommercial reproduction with attribution and requires prior written
authorization for commercial use. [DATA.GOV.HK terms](https://data.gov.hk/en/terms-and-conditions)
allow broader reuse of its Data and direct users of linked websites to those sites' terms.
The native inventory has no specific licence ID/title. These facts do not establish
a verified basis for this public API. Owner clarification on the intended use or
existing authorization remains pending. This is an operator hold, without a claim
that no authorization exists or that a provider denied network access.

PRs #170/#172 implement the three inspected map interfaces and reject explicit
failure envelopes, but their image was never deployed. During the owned rollout,
the linked notice was inspected. The pre-backup completed and restored independently;
no Worker/container activation occurred. Five original schedules were restored and
read back. Current controller/image remained the accepted HKSTP release
`ce9d6f6250832cc0d6bf6454575a8d58878645ff`, application version 84. Final readiness
passed, only the owned slot was released and the same source workers resumed.

The source guard blocks records before provider/cache access, including pinned
versions. Discovery and capability projections expose the source reuse review,
with no source-validation or failure writes. Dataset aliases inherit the hold.
Dated accepted facts remain intact. Request parameters and environment flags cannot
approve reuse; a reviewed basis must be recorded in code before public access.
Other source work and the complete frozen programme remain open.

The source dictionary independently specifies WGS 84 coordinates, average/surface
flow and CSV prediction fields: [official data specification](https://www.hydro.gov.hk/datagovhk/Hong_Kong_Tidal_Stream_Prediction_EN.pdf).
It does not resolve the public-reuse question. Geographic, period-file, timezone and language equivalence remain unqualified.
The publisher excludes navigation use.
