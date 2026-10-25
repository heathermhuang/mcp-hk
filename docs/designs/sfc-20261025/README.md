# Three dataset implementation handoffs

Prepared 25 October 2026, Asia/Singapore. These are execution plans, not evidence
that the three datasets have been collected, qualified or deployed.

The user authorised three separate implementation chats to complete engineering,
review, tests, merge, deployment and live acceptance. Routine reversible work and
releases within existing project authority should proceed. Provider outreach,
accepting new contracts, paid feeds, new paid infrastructure and additional
credentials are separate decisions when actually needed. Prepare the exact request
and complete independent engineering before asking; do not stop at a generic plan.

| Execution owner | Plan | Intended result |
|---|---|---|
| HKJC racing | [hkjc.md](hkjc.md) | Qualified results/profiles, historical coverage, and separately qualified prospective observations |
| SFC corporate verification | [sfc.md](sfc.md) | Exact corporate CE verification with dated official observations and purpose-limited output |
| HKEX Part XV disclosures | [hkex.md](hkex.md) | Issuer/filing discovery, complete bounded windows, amendment history and permitted read surfaces |

All three must read [shared execution requirements](shared.md) and the
[completed planning review](review.md). Individual plans specify dependencies,
work packages, contracts, tests, release gates and completion evidence. An unresolved
mode stays disabled, and is reported explicitly alongside completed engineering.
A deployed feature flag or synthetic fixture is never a live dataset acceptance.

## Repository and release baseline

The implementation repository is **heathermhuang/mcp-hk**, a separate repository
from this hk-app planning workspace. Remote main was verified on 25 October as
`9521ef6857e92250d35b45dca09337eb328ed3d2` (PR #70, UX release receipts).
Recheck current main before implementation; later accepted changes take precedence.

A clean reference clone is at
`/Users/heatherm/Documents/ChatGPT/hk-app/work/mcp-hk-ux-20261025`.
Do not reuse it for concurrent writes. Each chat should create an isolated clone
under `hk-app/work/` from current remote main, with its own `codex/` branch and test
database. Preserve the dirty primary `hk-app/projects/mcp-hk`, other worktrees,
untracked files, existing databases and running maintenance work. Inspect each
repository's current AGENTS.md and applicable release skills before execution.

Production source-aware UX is already released; its owning evidence is
`docs/verification/ux-20261025/RELEASED.md` in mcp-hk. Public app source was
`790ae5172fab6c86944f7eabea54780b72f09deb`; the later main merge records receipts.
The original Enigma archive is historical. Official CR observations are a different
version/source. Neither proves current SFC, HKEX or racing coverage.

The separate company-maintenance chat `01a16dec-cb5d-74e3-861e-d831059f5a47`
already owns CR backlog, address rotation, daily offsite RPO and its full live
matrix. Do not duplicate its jobs, source sweeps, automation or publication work.
Coordinate any shared backend/schema/host release through shared.md. Source work
can proceed independently while recovery or provider activation remains gated.

## Existing design and code references

- Parent: `docs/designs/mcp-hk-open-data-platform-implementation-plan.md`,
  `mcp-hk-open-data-platform-test-plan.md`,
  `mcp-hk-company-maintenance-next-implementation-plan.md` and
  `research/renavon-20261023/source-map.md`.
- mcp-hk: `AGENTS.md`, `docs/production.md`, `docs/curated-read-model.md`,
  `docs/data/qualification/company-permission-briefs.md` (SFC/HKEX briefs are unsent).
- Existing `curated/qualified_fixtures.py` and `tests/test_qualified_fixtures.py`
  are synthetic contracts, not collectors or permission evidence.
- Shared backend is `src/mcp_open_data_hk/curated/backend.py`; public surfaces
  are `api.py`, `server.py`, domain adapters, `connected.py`, source/pack contracts,
  web assets and generated discovery. Inspect current code before choosing edits.

## Planning source checks

Official pages were checked on 25 October. Their relevance and unresolved output
rights are recorded in each plan. HKJC's legacy results URL now redirects to a new
route; that is a parser/discovery concern, not a licence grant. The Directory
connector/CLI was unavailable; its public documentation was inspected, then
official provider pages supplied the source evidence. No service was purchased,
provisioned, contacted, or authorised through that lookup.

## Dispatch record

The reviewed plans were dispatched to three local hk-app execution chats:

| Source | Chat ID | Handoff |
|---|---|---|
| HKJC racing | `01a1716c-e3b3-7de1-91cf-58449c381316` | R01–R10; isolated racing clone, P8–P10 and source-family accounting |
| SFC | `01a1716d-2d97-7060-a100-052960204405` | S01–S09; exact corporate cohort, verification purpose and independent modes |
| HKEX | `01a1716d-9304-7231-85ce-7fbc21c764de` | H01–H10; issuer/window/revision completeness and DI route qualification |

Creation succeeded for all three. A bounded post-dispatch progress check confirmed
all three turns active: racing had created its isolated clone and was continuing
offline implementation while qualification remained unresolved; SFC was checking
permission evidence and preparing its implementation/verification workflow; HKEX
had its isolated clone and was proceeding with the disabled integration and source
qualification checks. These are initial progress observations, not completion.

Execution owners maintain their own source-specific status and evidence in mcp-hk;
this handoff does not replace the release runbook. No source implementation or live
activation is claimed by creating these chats.
