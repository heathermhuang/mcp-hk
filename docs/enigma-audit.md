# Enigma archive audit (offline operator tool)

The standalone `mcp-hk-enigma-audit` command acquires and audits David Webb's original Enigma release. It is not an MCP tool or public HTTP endpoint and changes no production state. Source data, credentials and working databases stay in a private scratch directory outside Git. The base application has no new database dependency.

## Source and attribution

- [Original release](https://drive.google.com/drive/folders/13mzAvvufXC3QmH8OvMVx2juUi7qdnVLL).
- Default file: `enigma251227.7z`, Drive ID `1AUpdv6nXd5G46dyUU-ydDL4rEUjbeoz5`, 1,721,680,391 bytes; provider modified time `2025-12-27T02:51:27.000Z`, rechecked on 23 October 2026.
- The original [notice](../src/mcp_open_data_hk/webb-site-NOTICE.txt) is shipped in the package and copied into the audit workspace with its checksum. Keep attribution to David M Webb / Webb-site with derived data. The Python project's MIT licence does not relicense the source dataset.
- A computed SHA-256 identifies our acquired bytes. It is not an independent publisher signature. The source configuration supports an upstream `sha256` when one is available. Refresh provider metadata before resuming a later acquisition; pass the verified source object through `--source-metadata` if it changed.

The Drive connector's 256 MB download limit is too small for this archive. The operator tool uses the public Google download flow, follows at most three validated same-source HTTPS redirects and refuses unrecognized access forms. It does not sign in, solve challenges or use a paid API.

## Dependencies and bounds

Use the project's locked Python environment, native 7-Zip (`7zz`) and a working local Docker runtime. The dump declares MySQL 8.0.37; the restore checks the official matching image digest. No arbitrary archive-supplied code, schema expressions, routines, triggers or collection software is executed.

Initial limits: 4 GiB download, 40 GiB declared extraction, 80 GiB scratch, 20 GiB free-disk reserve, 8 MiB SQL statement, 8 GiB monitored extractor resident memory, 30-minute extraction and one-hour import. The example MySQL container has a harder 6 GiB memory limit, two CPUs, no network and no published ports. Extraction memory is sampled, not an operating-system allocation guarantee. All extracted members write through bounded stdout into our opaque output filenames; archive paths never become filesystem destinations.

## Acquire and inspect

Choose a fresh private workspace. Preserve earlier failed/unknown receipts. Example:

```sh
export AUDIT_WORKSPACE=/private/tmp/mcp-enigma-audit
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit acquire --workspace "$AUDIT_WORKSPACE"
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit inspect --workspace "$AUDIT_WORKSPACE"
```

Acquisition checkpoints both the source fingerprint and the partial-byte checksum. Resume requires an exact byte-range response and matching validators where supplied; it never appends a full response to a partial file. A killed process's uncommitted tail is discarded only after validating the committed prefix. Completed bytes are verified before reusing them. A concurrent operator receives `AUDIT_BUSY` and does not alter the running job.

Read `archive-members.json` before choosing extraction members. The inspected release has separate Structure, Data and Triggers SQL files. Extract only Structure and Data for this audit:

```sh
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit extract --workspace "$AUDIT_WORKSPACE" --member 'enigmaStructure-2025-12-27- 000.sql'
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit extract --workspace "$AUDIT_WORKSPACE" --member 'enigmaData-2025-12-27- 000.sql'
```

Each extraction has an independent byte-count/hash/integrity receipt. A failed partial is retained under an attempt-specific name. Do not infer full restoration or dataset coverage from archive listing or extraction success.

## Disposable restore

Start only a new audit container and data directory. Do not point this tool at an existing application database. This example pins the official image observed during the audit:

```sh
mkdir -p "$AUDIT_WORKSPACE/mysql"
docker run -d --name mcp-hk-enigma-audit --network none --memory 6g --memory-swap 6g --cpus 2 --pids-limit 256 --security-opt no-new-privileges --env MYSQL_ALLOW_EMPTY_PASSWORD=yes --mount "type=bind,src=$AUDIT_WORKSPACE/mysql,dst=/var/lib/mysql" --tmpfs /tmp:rw,noexec,nosuid,size=268435456 mysql@sha256:598bf8b783dddc9070e9011aeb1eb5947f0bf7c4eda8ac510906556b8a2b6d0a --skip-networking --local-infile=OFF --event-scheduler=OFF --secure-file-priv=/var/lib/mysql-files --innodb-buffer-pool-size=1073741824 --innodb-redo-log-capacity=536870912 --innodb-flush-log-at-trx-commit=2 --skip-log-bin --performance-schema=OFF --max-allowed-packet=16777216
docker exec mcp-hk-enigma-audit mysqladmin -uroot ping
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit restore --workspace "$AUDIT_WORKSPACE" --container mcp-hk-enigma-audit --database audit_enigma
```

Wait for readiness before restore. The root account exists only inside this disconnected disposable container; no host port exposes it. The tool creates its own audit schema and gives the loader only SELECT/INSERT on audit data. Original source SQL is not piped to a privileged MySQL client: our parser verifies literal-only tuples and writes a field projection into tables built from approved primitive types. Source functions, expressions, triggers, foreign-key actions and automatic timestamps are not installed. INSERT is revoked for the completed audit database before verification. A failed/partial database is retained; retry requires a new explicit `audit_` name and still respects disk bounds.

The entire data dump is inventoried, while only company/name/officer/licence tables and supporting dimensions are restored. `people` omits HKID, ID-source links, dates of birth/death, title, sex and internal search/user fields. No raw person samples are emitted in the public audit report. `persons` is a shared source-ID registry, not the human-name table; names come from the projected `people` table.

## Evidence and qualification

`receipts.jsonl` is append-only and includes failed attempts. `acquisition.json`, member receipts, `source-schema.json`, `restore-progress.json` and `<database>-restore.json` describe different phases. Progress counters are submitted/scanned data, not confirmed committed counts. Only a successful restore reconciles every selected table's actual MySQL count with the parsed source count and records date/null ranges and source hashes. Empty/excluded tables remain visible in the source inventory.

This is an audit schema, not the future production read model. It does not claim complete current company data, point-in-time reconstruction or parity with Renavon's later additions. Field mappings, Hong Kong subset/relationship qualification, curated normalization and production backend sizing follow from the measured audit.

After committed-count verification, compare 100 stratified company records (including HK-listed offshore issuers), 30 name changes, 30 officer records and 30 licence intervals with the original dump:

```sh
PYTHONPATH=src .venv/bin/python -m mcp_open_data_hk.archive_audit qualify --workspace "$AUDIT_WORKSPACE" --container mcp-hk-enigma-audit --database audit_enigma
```

`archive-audit.json` records aggregate source-fidelity results, sampled-column names, ID-set digests, Hong Kong entity counts and observed MySQL storage. It does not publish sampled names or person identifiers. The comparisons verify import fidelity, not the truth/currentness of every upstream record. Full relationship closure, production PostgreSQL projection sizing and exhaustive reconciliation remain explicit next-stage requirements.

Stop the task-owned container when qualification is finished; retain the private files and failed receipts for inspection. Do not commit archive bytes, SQL data, credentials or Docker database files.

## Verification

```sh
PYTHONPATH=src .venv/bin/python -m pytest tests/test_archive_audit.py tests/test_archive_sql.py
bash scripts/check.sh all
```

The unit tests cover interruption/resume, changed partial/source identity, redirects, traversal/link/type limits, size/disk bounds, SQL injection/literal handling, correct field order and exclusion of sensitive columns. Full source restoration is separate recorded integration evidence and is not downloaded in ordinary CI.
