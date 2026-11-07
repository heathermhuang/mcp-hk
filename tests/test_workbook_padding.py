"""Workbook formatting must not count as populated source columns."""

import io

import pytest
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse


def workbook_bytes(rows, padding_column=None):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    if padding_column:
        book.active.cell(1, padding_column).fill = PatternFill(
            "solid", fgColor="FFFF00"
        )
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


@pytest.mark.parametrize("padding_column", [1001, 16384])
def test_formatting_only_columns_do_not_reject_a_small_table(padding_column):
    body = workbook_bytes(
        [["id", None, "value"], ["001", None, "=1+1"], ["002", False, 0]],
        padding_column,
    )
    rows, schema = parse(body, "XLSX")
    assert rows == [
        {"id": "001", "_column_2": None, "value": "=1+1"},
        {"id": "002", "_column_2": False, "value": 0},
    ]
    assert schema["sourceColumns"] == [
        {"name": "id", "sourceHeader": "id", "columnIndex": 1},
        {"name": "_column_2", "sourceHeader": "", "columnIndex": 2},
        {"name": "value", "sourceHeader": "value", "columnIndex": 3},
    ]


def test_later_rows_keep_values_beyond_the_first_rows_width():
    body = workbook_bytes([["id"], ["001", None, "extra"]], 16384)
    rows, schema = parse(body, "XLSX")
    assert rows == [{"id": "001", "_column_2": None, "_column_3": "extra"}]
    assert schema["sourceColumns"][-1]["columnIndex"] == 3


def test_previously_accepted_dimensions_keep_the_same_schema():
    body = workbook_bytes([["id"], ["001"]], 8)
    rows, schema = parse(body, "XLSX")
    assert len(schema["sourceColumns"]) == 8
    assert rows[0] == {"id": "001", **{"_column_" + str(i): None for i in range(2, 9)}}


def test_blank_first_row_keeps_positional_column_identity():
    body = workbook_bytes([[None], [None, "001", "=2+2"]], 16384)
    rows, schema = parse(body, "XLSX")
    assert rows == [{"_column_1": None, "_column_2": "001", "_column_3": "=2+2"}]
    assert [c["columnIndex"] for c in schema["sourceColumns"]] == [1, 2, 3]


@pytest.mark.parametrize("row", [1, 2])
def test_populated_columns_beyond_the_limit_are_still_rejected(row):
    rows = [["id"], ["001"]]
    rows[row - 1] = [None] * 1000 + ["source value"]
    with pytest.raises(DomainError, match="SOURCE_TOO_COMPLEX"):
        parse(workbook_bytes(rows), "XLSX")


def test_empty_sheet_is_not_turned_into_an_accepted_empty_table():
    with pytest.raises(DomainError, match="No table header"):
        parse(workbook_bytes([]), "XLSX")


def test_padding_does_not_bypass_the_row_limit(monkeypatch):
    monkeypatch.setattr("mcp_open_data_hk.resource_formats.MAX_ROWS", 1)
    body = workbook_bytes([["id"], ["001"], ["002"]], 16384)
    with pytest.raises(DomainError, match="SOURCE_TOO_LARGE"):
        parse(body, "XLSX")
