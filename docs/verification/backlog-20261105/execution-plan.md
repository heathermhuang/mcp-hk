# Complete frozen-resource execution plan

The deterministic `execution-plan.json.gz` contains one work item for every unique
resource referenced by the 5,584 family candidates or 1,653 residual groups in the
original `candidates.json.gz`: 8,324 resources. Original memberships, source URL
hashes, the checkpoint's status/validation times, accepted variant counts and the
next action are retained. Every original membership is covered; no source-status
or semantic approval is generated.

The input is the closed isolated database derived from accepted archive
`45ad2c6839db6c2bf8d507e5deb0b8d1fba7e8cc76c909afb7441f605e905d90` after its
provider-free client verification. `inputDatabaseSha256` identifies those actual
local bytes separately from the archive hash. The planner opens it read-only,
rejects a live WAL or changing file, makes zero provider requests and writes only
its output. Repeated execution produced byte-identical deterministic gzip.

| Work route at this checkpoint | Resources | Required next evidence |
|---|---:|---|
| Explicit selection pending | 3,408 | Published choice, exact selected read/query, cost and recovery |
| Dated accepted Census API-task link | 1,623 | Requested-scope/freshness check when needed; no original-file equivalence |
| Explicit native CSDI catalogue link | 637 | Native resource discovery and requested language/period/scope |
| Missing native catalogue link target | 2 | Reconcile exact official identifier; no invented replacement |
| Existing issue-scoped report adapter task | 486 | Explicit table/variable/presentation in the saved primary graph |
| Dated access denial | 301 | Changed source/access evidence before any retry |
| Internal capacity hold | 299 | Exact bound/scope retained; no silent budget increase |
| Unresolved failure cause | 451 | Separate provider failure from implementation error |
| Reader investigation | 135 | Exact failure and minimal original-source fixture before repair |
| Non-record map representation | 104 | An official feature representation for a record task |
| Existing transport parameter contract | 9 | Explicit native route/stop and current-source validation |
| Accepted scope needing remaining-choice review | 54 | Accepted selection and outstanding scopes, without whole-resource inference |
| Other representation/task triage | 815 | Demonstrated uncovered task and verified source contract |

These states route work; they do not assert that a whole resource is blocked or
accepted. In particular, the latest check can fail while other accepted variants
remain, and source-validation dates differ. Native catalogue links follow the
published `datasetId` exactly and verify its presence locally; they do not merge
entities or prove equivalent languages/periods. Map capabilities are not feature
records. Existing report adapter links are scoped task reuse, not source download
file equivalence. Raster/OCR/SQL/planner infrastructure remains deferred without a
demonstrated uncovered task, as specified in `PLAN.md`.

Reproduce from the verified closed checkpoint:

```sh
PYTHONPATH=src .venv/bin/python scripts/triage_backlog.py \
  /path/to/isolated/mcp-hk.sqlite3 \
  docs/verification/backlog-20261105/candidates.json.gz \
  docs/verification/backlog-20261105/wfs-release/census-adapter-task-audit.json.gz \
  execution-plan.json.gz
```

Source query values are omitted from the plan. Resource IDs and URL hashes link
back to the frozen/current native inventory; the source URL drift flag prevents a
changed source from being silently treated as the frozen representation. The
separate selection graph records actual operation evidence and remaining choices.
Planning coverage is complete; qualification and implementation remain open.
