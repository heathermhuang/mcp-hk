"""Source-fidelity samples and temporal/field qualification; no raw people export."""

import hashlib
import json
import re
import time
from pathlib import Path

from .archive_audit import AuditError, atomic_json, now, receipt
from .archive_restore import install_client_config, isolation, member_file, query
from .archive_sql import INSERT, MAX_STATEMENT, value_rows


def decode_literal(value, kind):
    if value == b"NULL":
        return None
    if value.startswith(b"'"):
        data = value[1:-1]
        out, i = bytearray(), 0
        escape = {
            ord("0"): 0,
            ord("n"): 10,
            ord("r"): 13,
            ord("t"): 9,
            ord("b"): 8,
            ord("Z"): 26,
        }
        while i < len(data):
            if data[i : i + 2] == b"''":
                out.append(39)
                i += 2
            elif data[i] == 92:
                if i + 1 >= len(data):
                    raise AuditError("INVALID_LITERAL", "Incomplete source escape")
                if data[i + 1] in b"%_":
                    out.append(92)
                out.append(escape.get(data[i + 1], data[i + 1]))
                i += 2
            else:
                out.append(data[i])
                i += 1
        return out.decode("utf-8")
    if re.fullmatch(rb"[+-]?[0-9]+", value):
        return int(value)
    if kind in {"float", "double", "decimal"}:
        return float(value)
    raise AuditError(
        "SAMPLE_TYPE_UNSUPPORTED",
        "Sample contains a type requiring explicit normalization",
    )


def comparable(value, kind):
    if (
        isinstance(value, str)
        and kind in {"datetime", "timestamp", "time"}
        and "." in value
    ):
        whole, fraction = value.rsplit(".", 1)
        if fraction.isdigit():
            fraction = fraction.rstrip("0")
            return whole + ("." + fraction if fraction else "")
    return value


def sample_rows(
    container, database, table, columns, where="1", limit=30, reverse=False
):
    order = "DESC" if reverse else "ASC"
    select = "JSON_ARRAY(" + ",".join(f"`{c}`" for c in columns) + ")"
    result = query(
        container,
        database,
        f"SET SESSION max_execution_time=120000; SELECT {select} FROM `{table}` WHERE {where} ORDER BY `{columns[0]}` {order} LIMIT {limit};",
    )
    return [json.loads(line) for line in result.split("\n") if line]


def qualify(workspace, container, database):
    if not re.fullmatch(r"audit_[a-z0-9_]{1,50}", database):
        raise AuditError("UNSAFE_DATABASE", "Use a recorded audit database")
    restore = json.loads((workspace / f"{database}-restore.json").read_text())
    if restore.get("status") != "restored":
        raise AuditError(
            "RESTORE_INCOMPLETE",
            "Committed counts must be verified before qualification",
        )
    isolation(workspace, container)
    install_client_config(workspace, container)
    schemas = json.loads((workspace / "source-schema.json").read_text())
    data, data_proof = member_file(workspace, "Data")
    samples = {}
    comparison_columns = {}
    hk_domicile = int(
        query(container, database, "SELECT ID FROM domiciles WHERE A2='HK';").strip()
    )
    strata = {}
    for table in ["organisations", "namechanges", "directorships", "licrec"]:
        allowed = restore["restoredTableAudit"][table]["columns"]
        columns = [
            c["name"]
            for c in schemas[table]["columns"]
            if c["name"] in allowed
            and not c["type"].startswith(("bit", "binary", "varbinary"))
        ]
        comparison_columns[table] = columns
        if table == "organisations":
            groups = [
                (f"Domicile={hk_domicile} AND incDate<'1980-01-01'", False),
                (
                    f"Domicile={hk_domicile} AND incDate>='2000-01-01' AND disDate IS NULL",
                    True,
                ),
                (f"Domicile={hk_domicile} AND disDate IS NOT NULL", False),
                (f"Domicile={hk_domicile} AND cName IS NOT NULL AND cName<>''", True),
                (
                    f"Domicile<>{hk_domicile} AND PersonID IN (SELECT issuer FROM issue WHERE ID1 IN (SELECT IssueID FROM stocklistings WHERE StockExID IN (SELECT stockExID FROM listings WHERE shortName IN ('HK Main','HK GEM'))))",
                    False,
                ),
            ]
            found, remaining = {}, []
            for index, (where, reverse) in enumerate(groups):
                count = 0
                for row in sample_rows(
                    container,
                    database,
                    table,
                    columns,
                    where,
                    limit=60,
                    reverse=reverse,
                ):
                    if row[0] in found:
                        continue
                    if count < 20:
                        found[row[0]] = row
                        count += 1
                    else:
                        remaining.append(row)
                strata[str(index + 1)] = count
            for row in remaining:
                if len(found) == 100:
                    break
                found.setdefault(row[0], row)
            samples[table] = found
        else:
            samples[table] = {
                row[0]: row for row in sample_rows(container, database, table, columns)
            }
    required = {
        "organisations": 100,
        "namechanges": 30,
        "directorships": 30,
        "licrec": 30,
    }
    if any(len(samples[t]) != count for t, count in required.items()):
        raise AuditError(
            "SAMPLE_COVERAGE", "Required source-fidelity sample is incomplete"
        )
    matched = {table: set() for table in samples}
    expressions = {
        table: re.compile(
            rb"(?:^|,)\((?:" + b"|".join(str(i).encode() for i in rows) + rb"),"
        )
        for table, rows in samples.items()
    }
    started = time.monotonic()
    with data.open("rb") as source:
        while line := source.readline(MAX_STATEMENT + 1):
            if len(line) > MAX_STATEMENT:
                raise AuditError(
                    "STATEMENT_LIMIT", "Sample scan exceeded the statement bound"
                )
            header = INSERT.match(line)
            if not header:
                continue
            table = header[1].decode()
            if table not in samples or len(matched[table]) == len(samples[table]):
                continue
            payload = line[header.end() :].strip()
            if not expressions[table].search(payload):
                continue
            columns = schemas[table]["columns"]
            projected = [
                i
                for i, c in enumerate(columns)
                if c["name"] in comparison_columns[table]
            ]
            for values in value_rows(payload, len(columns)):
                source_id = int(values[0])
                if source_id not in samples[table]:
                    continue
                actual = [
                    decode_literal(values[i], columns[i]["type"].split("(")[0])
                    for i in projected
                ]
                kinds = [columns[i]["type"].split("(")[0] for i in projected]
                normalized_source = [comparable(v, k) for v, k in zip(actual, kinds)]
                normalized_database = [
                    comparable(v, k) for v, k in zip(samples[table][source_id], kinds)
                ]
                if normalized_source != normalized_database:
                    expected = samples[table][source_id]
                    differences = []
                    for index, (left, right) in enumerate(zip(actual, expected)):
                        if left != right:
                            column = columns[projected[index]]
                            item = {
                                "column": column["name"],
                                "type": column["type"],
                                "sourceValueType": type(left).__name__,
                                "restoredValueType": type(right).__name__,
                            }
                            if column["type"].split("(")[0] in {
                                "date",
                                "datetime",
                                "timestamp",
                            }:
                                item.update(sourceDate=left, restoredDate=right)
                            differences.append(item)
                    atomic_json(
                        workspace / f"sample-mismatch-{time.time_ns()}.json",
                        {
                            "table": table,
                            "sourceId": source_id,
                            "differences": differences,
                        },
                    )
                    raise AuditError(
                        "SAMPLE_MISMATCH",
                        f"Restored source facts differ in {table}; preserve private evidence",
                    )
                matched[table].add(source_id)
            if all(len(matched[t]) == len(samples[t]) for t in samples):
                break
    if any(len(matched[t]) != len(samples[t]) for t in samples):
        raise AuditError(
            "SAMPLE_MISSING", "Could not locate every selected row in the original dump"
        )
    stats = query(
        container,
        database,
        "SELECT table_name,data_length,index_length,table_rows FROM information_schema.tables WHERE table_schema=DATABASE() ORDER BY table_name;",
    )
    hk_count = query(
        container,
        database,
        f"SELECT COUNT(*) FROM organisations WHERE Domicile={hk_domicile};",
    ).strip()
    report = {
        "status": "source_fidelity_verified",
        "qualifiedAt": now(),
        "database": database,
        "sourceDataSha256": data_proof["sha256"],
        "samples": {
            t: {
                "count": len(matched[t]),
                "columns": comparison_columns[t],
                "sourceIdSetSha256": hashlib.sha256(
                    json.dumps(sorted(matched[t])).encode()
                ).hexdigest(),
            }
            for t in samples
        },
        "sourceScanAndMeasurementsSeconds": round(time.monotonic() - started, 3),
        "auditorModuleSha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("archive_*.py")
        },
        "hongKongDomiciledSourceEntities": int(hk_count),
        "companyStrataSampleCounts": strata,
        "mysqlTableStorage": [
            dict(
                zip(
                    ["table", "dataBytes", "indexBytes", "approximateRows"],
                    line.split("\t"),
                )
            )
            for line in stats.splitlines()
        ],
        "qualifications": [
            "Samples compare restored projected facts with the original archive; they are not current-government verification or a population accuracy estimate.",
            "Redundant fractional-second zeroes in MySQL JSON timestamp rendering are compared semantically; source fact values are not rewritten.",
            "incID is a source/domicile registry identifier, not a verified universal BRN crosswalk.",
            "namechanges records previous names and change dates; effective-start dates must not be guessed.",
            "directorships contains global officer/other roles, not solely HK-listed company directors.",
            "licrec and olicrec are activity/relationship intervals, not counts of distinct licensed people or firms.",
            "Source raw tables and sampled source IDs remain private; no source records are published by this audit.",
            "Full Hong Kong relationship closure, exhaustive foreign-key reconciliation and production PostgreSQL query sizing remain projection-stage work.",
        ],
    }
    atomic_json(workspace / "archive-audit.json", report)
    receipt(
        workspace, "qualify", "verified", samples=sum(len(m) for m in matched.values())
    )
    return report
