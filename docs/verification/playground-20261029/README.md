# Data playground local candidate — 2026-10-29

Candidate branch: `codex/data-playground`, based on `8504d79`. The implementation
checkout is `work/mcp-hk-playground-20261029` in the umbrella workspace. The planning
checkout and unrelated primary files were preserved. This is a local candidate:
there is no remote PR, CI receipt, deployment, production mutation or usability pilot.

The complete family interface is implemented in [the workspace guide](../../data-playground.md).
Source availability, rights, activation, statistical currency and completeness remain
separate from integration. Fixture reads do not qualify a live provider.

## Verification receipts

- Required entrypoint: `PYTHONPATH=src bash scripts/check.sh all`. Python 3.12.13:
  **728 passed, 122 skipped**; Black/Flake8 passed. Worker types, TypeScript and
  **166 Node tests** passed on Node 24.18.0. The normal sandbox could not bind the
  local Wrangler listener; the successful local run permitted that listener.
- New API tests cover typed HTTP/MCP parity, legacy equality, mixed kinds, large
  integers, integral floats, negative zero, literal dotted keys, null/missing,
  finite/value bounds, duplicate/mixed predicates, whole-envelope/sidecar bytes,
  accepted-count paging, busy/deadline and actual worker-completion cleanup.
- The all-family headless suite exercises source selection and restrictions,
  workbook/layer/path/parameter choices, documents, draft/apply, obsolete queries,
  detail/export cancellation, cooldown, version drift, source-specific feeds,
  issuer resolution, SFC activation, arrivals TTL, views, downloads, clipboard
  fallback, focus return, English/Traditional Chinese and 320/390/768/1280 layouts.
  Dark theme and reduced motion are exercised. See `playground-browser.json`.
- A second headless suite uses the **actual local Python API** with invented data
  seeded through the parser and accepted cache. It verifies a two-request open,
  no keystroke read, repeated exact filters, unsafe integers, int/float and
  null/missing distinctions, version pins and downloaded evidence. It uses no
  provider request or intercepted query response. A 100-column wide/nested fixture
  then advances through four pages and proves that only three are retained: collected
  heap grew from 2,404,180 to 5,661,044 bytes (3,256,864-byte delta; a 32 MiB smoke
  ceiling, not a device-wide guarantee). See `real-api-browser.json`.
- Existing directory browser journeys: **8 cases**, no page errors. Existing
  unified company/disclosure/SFC journeys: **8 cases**, no page errors. Whole-site
  static content/navigation: **168 route/locale/viewport cases**, no page errors.
- Independent Python ZIP/CSV readers check actual Unicode bytes, member CRCs and
  SHA-256 hashes, formula escaping, leading zeros, unsafe numeric spreadsheet text,
  exact JSON and manifest row scope. Export and feed legacy regressions pass.
- Worker/Python route tests compare generated bilingual HTML, canonical/filtered
  metadata, no-JS links, family recipes and non-reflection of private queries.
  Analytics tests verify existing consent and pathname-only collection for
  playground fragments and query inputs.

Local screenshots and downloaded ZIPs are in the ignored `playwright-artifacts/`
folders. Reproducible browser runners are under `deploy/cloudflare/`; the new suites
are included in the existing UX CI workflow. Generated discovery assets are rebuilt,
not checked in as authored pages.

Python 3.10/3.11 source grammar checks passed, but those runtimes are not installed
here. Node 22 is also unavailable locally. Their required runtime CI jobs remain
unverified. Optional PostgreSQL/live-provider environments behind the existing skips
were not supplied. No outside/Claude review or nontechnical human testing is claimed.

## Local resource cost

`benchmark.json` preserves the first controlled interleaved comparison with the
baseline and candidate using the same Python 3.12.13 environment. Two process rounds
reverse baseline/candidate order; each has nine query samples (18 per arm/scenario).
Input rows, fields, bytes, wall/CPU time, response bytes, process peak RSS, and a
5 ms SQLite maintenance heartbeat during two readers are recorded. Provider/network
latency is excluded. Candidate samples request the exact sidecar; baseline does not.

| Synthetic workload | Baseline median / p95 ms | Candidate median / p95 ms | Response bytes baseline → candidate |
|---|---:|---:|---:|
| Warm 10,000 rows | 1.966 / 3.397 | 0.239 / 1.387 | 1,908 → 7,244 |
| Warm 100,000 rows | 18.953 / 20.584 | 0.242 / 1.541 | 1,909 → 7,245 |
| Filtered 100,000 rows | 42.753 / 46.744 | 37.501 / 38.530 | 849 → 1,399 |
| Nested/wide 10,000 rows | 2.006 / 3.355 | 0.246 / 1.703 | 5,872 → 12,631 |
| File-backed 100,000 rows | 1,162.631 / 1,172.975 | 725.125 / 736.028 | 1,909 → 7,245 |

Unfiltered queries now use the accepted exact count and stop after the requested
page. Filtered equality still scans for an exact total. Single-pass scalar-kind
metadata avoids a cold-parse regression in this comparison. The opt-in sidecar
costs bytes; the 1,536,000-byte whole-response cap includes them.

The initial disk-overlap heartbeat had a longer candidate pause (112.75 ms vs
73.37 ms). File validation now yields the GIL every 4,096 rows. The first follow-up
(`file-overlap-followup.json`) overlapped a browser suite and is retained as a
contended diagnostic, not acceptance evidence. `file-overlap-final.json` is the
quiet targeted rerun after that correction: baseline maximum heartbeat pause
190.07 ms; candidate 76.29 ms, with approximately 1,163 ms vs 726 ms median
file-query time. These varying tails are reported rather than selected away. Do not infer production maintenance
headroom from a local synthetic heartbeat, or treat its maximum as a stable SLO.

Reproduce without any provider call:

```sh
PYTHONPATH=src .venv/bin/python scripts/benchmark_playground.py \
  --baseline ../mcp-hk-directory-20261029 \
  --output /tmp/playground-comparison.json
```

The browser retains at most three page results; no unbounded record accumulation,
all-family status fan-out, background arrival polling, distinct-values scan, or
all-pages export is introduced. Production quotas and schedules were not increased.

## Build compatibility

Wheel and source distribution builds succeeded through the declared setuptools
backend using cached setuptools 84.2.1 and wheel 0.48.0, with no dependency download
or modification of the shared locked runtime. Independent archive inspection found
all new backend/browser modules and source documentation. The `build` wrapper and
setuptools were absent from the test venv; direct backend invocation supplied the
cached build tools instead. This is local package validation, not a publishing run.

## Review and release boundary

Local review corrected stale filter event references, paging with unapplied drafts,
edit loss during reads, source-choice persistence, numeric spreadsheet rounding,
late detail/export completion, inactive source-mode handling, source-specific history capabilities and large-reader
cooperation. Source-specific versions/cursors and original export notices remain
owned by their existing adapters. No remaining blocking local correctness finding
is known after those corrections; this is the implementing agent's review.

Publication requires explicit authorization to push this branch and open a PR.
Merge/deployment also require explicit authorization, exact-candidate green CI,
live headroom verification, coordinated controller/container/assets adoption,
HTTP/MCP regressions, schedule restoration and a fresh accepted-backup isolated
restore under [production.md](../../production.md). The five-person usability pilot
and live source acceptance remain distinct release gates. Local code or screenshots
do not establish either.
