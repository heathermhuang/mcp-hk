# KMB same-stop published label repair

Actual adopted-release HTTP/MCP checked route 1 but route 103 failed mapping, then
11C/11K remained unchecked at the unchanged lookup bound. Source investigation
proved direction O and current native names/locations were valid. The accepted TD
stop 4001 publishes a combined route label containing `/<br>` and separately an
explicit `[KMB] CHUK YUEN ESTATE BUS TERMINUS` / `[KMB] 竹園邨總站` label. The old
candidate construction overwrote the same-ID stop labels with the combined path
label, making exact comparison fail and waste unrelated-stop lookups.

Preserve original same-ID bilingual stop labels alongside the route label. Only
explicit single-company KMB/LWB tags matching the candidate's operator are accepted
as additional exact names. Mixed-company/HTML labels are not split into guessed
aliases, and unlabelled/other-company text cannot qualify. Native names, pole codes,
IDs, 35m locations, repeated visits and current order retain their existing checks.
No global identity crosswalk, looser distance/name match or budget increase is added.

Four new regressions cover the real combined-label shape, wrong company, unlabelled
text and a distant stop. A local candidate/actual production resource-path rehearsal
verified routes 1 and 103; its paced wrapper retained two unchecked references at
the same 45-second deadline. This is not new-code production HTTP/MCP proof; exact-
head CI, deployment, actual comparisons and fresh recovery remain required.
