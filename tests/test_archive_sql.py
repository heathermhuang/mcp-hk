"""Literal-only import must preserve source facts without executing source SQL."""

import io

import pytest

from mcp_open_data_hk.archive_audit import AuditError
from mcp_open_data_hk.archive_sql import (
    audit_ddl,
    scan_dump,
    schema_inventory,
    value_rows,
)


SCHEMA = """CREATE TABLE `people` (
  `PersonID` int unsigned NOT NULL,
  `HKID` varchar(8) DEFAULT NULL,
  `Name1` varchar(90) DEFAULT NULL,
  `Name2` varchar(63) DEFAULT NULL,
  `cName` varchar(20) DEFAULT NULL,
  `SFCID` varchar(6) DEFAULT NULL,
  `modified` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `SFCupd` datetime DEFAULT NULL,
  `SFClastDate` date DEFAULT NULL,
  PRIMARY KEY (`PersonID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def test_ddl_preserves_types_but_drops_expressions_and_sensitive_columns(monkeypatch):
    monkeypatch.setattr(
        "mcp_open_data_hk.archive_sql.SELECTED", {"people": ["PersonID", "Name1"]}
    )
    ddl = audit_ddl(schema_inventory(SCHEMA))
    assert "`PersonID` int unsigned NOT NULL" in ddl
    assert "PRIMARY KEY (`PersonID`)" in ddl
    assert "HKID" not in ddl
    assert "CURRENT_TIMESTAMP" not in ddl
    assert "ON UPDATE" not in ddl


def test_sensitive_fields_are_not_sent_to_database(tmp_path):
    data = tmp_path / "source.sql"
    data.write_bytes(
        b"INSERT INTO `people` VALUES (4,'PRIVATE','O\\'Brien','A',NULL,'ABC123','2025-01-02',NULL,NULL);\n"
    )
    sink = io.BytesIO()
    report = scan_dump(data, schema_inventory(SCHEMA), sink)
    assert report["tables"]["people"]["rows"] == 1
    assert b"PRIVATE" not in sink.getvalue()
    assert b"HKID" not in sink.getvalue()
    assert b"O\\'Brien" in sink.getvalue()
    assert b"`PersonID`,`Name1`,`Name2`" in sink.getvalue()


@pytest.mark.parametrize(
    "payload",
    [
        b"(SLEEP(100));",
        b"(LOAD_FILE('/etc/passwd'));",
        b"(1);DROP TABLE people;",
        b"(1),(2);SELECT 1;",
        b"(1)/* comment */;",
        b"('unterminated);",
        b"(1,2);",
    ],
)
def test_nonliteral_sql_and_column_mismatches_are_rejected(payload):
    with pytest.raises(AuditError):
        list(value_rows(payload, 1))


def test_escaped_delimiters_unicode_binary_and_null_are_literal_values():
    row = list(
        value_rows("('鴨巴甸街,(x);',NULL,0xF00D,b'1',-3.5e+2,'O''Brien');".encode(), 6)
    )[0]
    assert row[0] == "'鴨巴甸街,(x);'".encode()
    assert row[1:] == [b"NULL", b"0xF00D", b"b'1'", b"-3.5e+2", b"'O''Brien'"]


def test_source_statements_cannot_reach_the_database(tmp_path):
    data = tmp_path / "source.sql"
    data.write_text("DROP DATABASE audit;\n")
    sink = io.BytesIO()
    with pytest.raises(AuditError, match="Unsupported"):
        scan_dump(data, schema_inventory(SCHEMA), sink)
    assert not sink.getvalue()


def test_entire_insert_is_validated_before_sending_any_projected_row(tmp_path):
    data = tmp_path / "source.sql"
    data.write_text(
        "INSERT INTO `people` VALUES (1,NULL,'A',NULL,NULL,NULL,NULL,NULL,NULL),(2,LOAD_FILE('bad'),NULL,NULL,NULL,NULL,NULL,NULL,NULL);\n"
    )
    sink = io.BytesIO()
    with pytest.raises(AuditError):
        scan_dump(data, schema_inventory(SCHEMA), sink)
    assert not sink.getvalue()


def test_nonselected_table_is_counted_but_not_restored(tmp_path):
    schemas = schema_inventory(SCHEMA.replace("people", "unrelated"))
    data = tmp_path / "source.sql"
    data.write_text(
        "INSERT INTO `unrelated` VALUES (1,NULL,'A',NULL,NULL,NULL,NULL,NULL,NULL);\n"
    )
    sink = io.BytesIO()
    assert scan_dump(data, schemas, sink)["tables"]["unrelated"]["rows"] == 1
    assert not sink.getvalue()


def test_unsupported_schema_does_not_produce_a_partial_inventory():
    with pytest.raises(AuditError):
        schema_inventory(SCHEMA + "CREATE TABLE `bad` unsupported;")


def test_mysql_column_names_with_punctuation_are_inventoried():
    schema = SCHEMA.replace("`HKID`", "`D&Afinal`")
    result = schema_inventory(schema)
    assert len(result["people"]["columns"]) == 9
    assert result["people"]["columns"][1]["name"] == "D&Afinal"
