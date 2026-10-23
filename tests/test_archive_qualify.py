import pytest

from mcp_open_data_hk.archive_audit import AuditError
from mcp_open_data_hk.archive_qualify import comparable, decode_literal


def test_mysql_literal_comparison_preserves_null_unicode_and_escape_semantics():
    assert decode_literal(b"NULL", "varchar") is None
    assert decode_literal(b"'NULL'", "varchar") == "NULL"
    assert decode_literal(b"'O\\'Brien'", "varchar") == "O'Brien"
    assert decode_literal(b"'O''Brien'", "varchar") == "O'Brien"
    assert decode_literal(b"'A\\nB\\0'", "varchar") == "A\nB\0"
    assert decode_literal("'鴨巴甸街'".encode(), "varchar") == "鴨巴甸街"
    assert decode_literal(b"'000123'", "varchar") == "000123"
    assert decode_literal(b"'0000-00-00'", "date") == "0000-00-00"
    assert decode_literal(b"123", "int") == 123


def test_unknown_sample_types_are_not_silently_normalized():
    with pytest.raises(AuditError):
        decode_literal(b"b'1'", "bit")


def test_mysql_json_fractional_second_rendering_does_not_fabricate_a_mismatch():
    assert comparable("2016-01-18 13:32:21.000000", "timestamp") == comparable(
        "2016-01-18 13:32:21", "timestamp"
    )
    assert comparable("2016-01-18 13:32:21.120000", "datetime") == comparable(
        "2016-01-18 13:32:21.12", "datetime"
    )
    assert comparable("2016-01-18 13:32:21.000001", "datetime") != comparable(
        "2016-01-18 13:32:21", "datetime"
    )
    assert comparable("001.00", "varchar") == "001.00"
