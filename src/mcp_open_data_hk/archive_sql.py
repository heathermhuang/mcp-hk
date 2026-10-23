"""Read mysqldump literals; generate our own allowlisted audit DDL/INSERTs."""

import re

from .archive_audit import AuditError

MAX_STATEMENT = 8 * 1024 * 1024
TABLE = re.compile(r"CREATE TABLE `([A-Za-z0-9_]+)` \(\n(.*?)\n\) ENGINE[^\n]+", re.S)
COLUMN = re.compile(r"^  `([^`\r\n]+)` ([a-z]+)(\([0-9,]+\))?( unsigned)?", re.M)
PRIMARY = re.compile(r"PRIMARY KEY \(([^)]+)\)")
INSERT = re.compile(rb"INSERT INTO `([A-Za-z0-9_]+)` VALUES ")
LITERAL = re.compile(
    rb"(?:0x[0-9a-fA-F]*|_binary\s*'(?:[^'\\]|\\.|'')*'|b'[01]*'|NULL|"
    rb"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|"
    rb"'(?:[^'\\]|\\.|'')*')",
    re.S,
)
TYPES = {
    "tinyint",
    "smallint",
    "mediumint",
    "int",
    "bigint",
    "float",
    "double",
    "decimal",
    "char",
    "varchar",
    "binary",
    "varbinary",
    "bit",
    "date",
    "time",
    "datetime",
    "timestamp",
    "year",
    "text",
    "mediumtext",
    "longtext",
    "blob",
    "mediumblob",
    "longblob",
    "tinytext",
    "tinyblob",
}
SELECTED = {
    "organisations": "PersonID Domicile Name1 cName SFCID orgType incDate disDate disMode incAcc incID incUpd modified SFCupd SFCri".split(),
    "people": "PersonID Name1 Name2 cName SFCID modified SFCupd SFClastDate".split(),
    "namechanges": "ID1 personID oldName oldcName dateChanged dateAcc modified".split(),
    "directorships": "ID1 Company Director JoinedY ApptDate ApptAcc ResDate ResAcc positionID source modified".split(),
    "licrec": "ID staffID orgID role actType startDate endDate modified".split(),
    "olicrec": "ID orgID ri actType startDate endDate modified".split(),
    "domiciles": None,
    "orgtypes": None,
    "dismodes": None,
    "positions": None,
    "activity": None,
    "dateaccuracy": None,
    "issue": None,
    "listings": None,
    "stocklistings": None,
}


def schema_inventory(text):
    result = {}
    for table, body in TABLE.findall(text):
        columns = []
        for name, kind, dimensions, unsigned in COLUMN.findall(body):
            columns.append({"name": name, "type": kind + dimensions + unsigned})
        if len(columns) != len(re.findall(r"^  `", body, re.M)):
            raise AuditError(
                "SCHEMA_UNSUPPORTED", f"Could not recognize every column in {table}"
            )
        primary = PRIMARY.search(body)
        result[table] = {
            "columns": columns,
            "primaryKey": re.findall(r"`([^`]+)`", primary[1]) if primary else [],
        }
    if not result or len(result) != text.count("CREATE TABLE `"):
        raise AuditError("SCHEMA_UNSUPPORTED", "Could not inventory every source table")
    return result


def audit_ddl(schemas):
    statements = []
    for table, selected in SELECTED.items():
        if table not in schemas:
            raise AuditError("MISSING_TABLE", f"Required audit table absent: {table}")
        schema = schemas[table]
        selected = selected or [c["name"] for c in schema["columns"]]
        known = {c["name"]: c["type"] for c in schema["columns"]}
        if set(selected) - known.keys():
            raise AuditError("MISSING_FIELD", f"Required audit field absent in {table}")
        fields = []
        for name in selected:
            kind = known[name]
            if kind.split("(")[0].split()[0] not in TYPES:
                raise AuditError(
                    "TYPE_UNSUPPORTED", f"Unsupported audit type in {table}"
                )
            # No source expressions, constraints, routines, triggers or comments.
            if kind.startswith("timestamp"):
                kind = "datetime"
            nullable = "NOT NULL" if name in schema["primaryKey"] else "NULL"
            fields.append(f"`{name}` {kind} {nullable}")
        keys = schema["primaryKey"]
        if keys and set(keys) <= set(selected):
            fields.append("PRIMARY KEY (" + ",".join(f"`{k}`" for k in keys) + ")")
        statements.append(
            f"CREATE TABLE `{table}` ("
            + ",".join(fields)
            + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        )
    return "\n".join(statements)


def value_rows(payload, columns):
    """Yield only literal tuples. Reject SQL expressions and stacked statements."""
    pos, size = 0, len(payload)
    while pos < size:
        if payload[pos : pos + 1] != b"(":
            raise AuditError("INVALID_INSERT", "Expected a literal tuple")
        pos += 1
        row = []
        while True:
            match = LITERAL.match(payload, pos)
            if not match:
                raise AuditError("INVALID_LITERAL", "Nonliteral SQL value refused")
            row.append(match[0])
            pos = match.end()
            separator = payload[pos : pos + 1]
            pos += 1
            if separator == b")":
                break
            if separator != b",":
                raise AuditError("INVALID_INSERT", "Unexpected literal delimiter")
        if len(row) != columns:
            raise AuditError("COLUMN_MISMATCH", "Source row does not match its schema")
        yield row
        if pos == size - 1 and payload[pos : pos + 1] == b";":
            return
        if payload[pos : pos + 1] != b",":
            raise AuditError("INVALID_INSERT", "Unexpected SQL after tuple")
        pos += 1
    raise AuditError("INVALID_INSERT", "Unterminated source INSERT")


def preflight_columns(path, schemas):
    seen = set()
    with path.open("rb") as source:
        while line := source.readline(MAX_STATEMENT + 1):
            if len(line) > MAX_STATEMENT:
                raise AuditError(
                    "STATEMENT_LIMIT", "Dump statement exceeds 8 MiB bound"
                )
            match = INSERT.match(line)
            if not match:
                continue
            table = match[1].decode()
            if table not in schemas:
                raise AuditError(
                    "UNKNOWN_TABLE", "Source data table missing from schema"
                )
            if table not in seen:
                next(
                    value_rows(
                        line[match.end() :].strip(), len(schemas[table]["columns"])
                    )
                )
                seen.add(table)
    return {
        "dataTablesChecked": len(seen),
        "emptySchemaTables": sorted(set(schemas) - seen),
    }


def scan_dump(path, schemas, sink=None, progress=None):
    """One bounded line at a time; inventory all rows, restore only selected fields."""
    counts = {name: {"rows": 0, "insertStatements": 0} for name in schemas}
    source_bytes = 0
    with path.open("rb") as source:
        for line_number in range(1, 1000000000):
            line = source.readline(MAX_STATEMENT + 1)
            if not line:
                break
            source_bytes += len(line)
            if len(line) > MAX_STATEMENT:
                raise AuditError(
                    "STATEMENT_LIMIT", "Dump statement exceeds 8 MiB bound"
                )
            line = line.strip()
            if not line or line.startswith(
                (b"--", b"/*!", b"LOCK TABLES", b"UNLOCK TABLES", b"USE `")
            ):
                continue
            match = INSERT.match(line)
            if not match:
                raise AuditError(
                    "UNEXPECTED_SQL",
                    f"Unsupported data statement at line {line_number}",
                )
            table = match[1].decode("ascii")
            if table not in schemas:
                raise AuditError(
                    "UNKNOWN_TABLE", "Data table missing from schema inventory"
                )
            columns = schemas[table]["columns"]
            selected = SELECTED.get(table) or [c["name"] for c in columns]
            indexes = [i for i, c in enumerate(columns) if c["name"] in selected]
            # Keep the source order, not the declaration order of the projection.
            names = [columns[i]["name"] for i in indexes]
            restored = []
            rows = 0
            for values in value_rows(line[match.end() :], len(columns)):
                rows += 1
                if sink is not None and table in SELECTED:
                    restored.append(b"(" + b",".join(values[i] for i in indexes) + b")")
            counts[table]["rows"] += rows
            counts[table]["insertStatements"] += 1
            if restored:
                header = (
                    f"INSERT INTO `{table}` ("
                    + ",".join(f"`{n}`" for n in names)
                    + ") VALUES "
                )
                sink.write(header.encode() + b",".join(restored) + b";\n")
            if progress and counts[table]["insertStatements"] % 100 == 0:
                progress(table, source_bytes, counts)
    return {
        "tables": counts,
        "sourceBytes": source_bytes,
        "schemaTableCount": len(schemas),
    }
