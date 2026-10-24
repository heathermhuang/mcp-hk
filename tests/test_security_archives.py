"""Synthetic record/workbook expansion controls; no source network access."""

import io
import zipfile

import pytest
from openpyxl import Workbook

from mcp_open_data_hk import resource_formats as formats
from mcp_open_data_hk.contracts import DomainError


def zipped(members):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return out.getvalue()


@pytest.mark.parametrize(
    "name", ["nested.csv", "nested.json", "ignored.bin", "empty.csv"]
)
def test_nested_containers_rejected_before_child_expansion(name):
    child = zipped([] if name.startswith("empty") else [("rows.csv", b"a\n1\n")])
    with pytest.raises(DomainError) as error:
        formats.parse(zipped([("valid.csv", b"a\n1\n"), (name, child)]), "CSV")
    assert error.value.code == "NESTED_ARCHIVE"


def test_disguised_workbook_does_not_bypass_flat_archive_policy():
    with pytest.raises(DomainError) as error:
        formats.parse(zipped([("nested.xlsx", zipped([("data.csv", b"a\n1")]))]), "CSV")
    assert error.value.code == "NESTED_ARCHIVE"


def test_shared_actual_expansion_and_member_limits(monkeypatch):
    payload = zipped([("a.csv", b"a\n" + b"x" * 55), ("b.csv", b"b\n" + b"x" * 55)])
    monkeypatch.setattr(formats, "MAX_EXPANDED_BYTES", 100)
    with pytest.raises(DomainError) as error:
        formats.parse(payload, "CSV")
    assert error.value.code == "SOURCE_TOO_LARGE"
    monkeypatch.setattr(formats, "MAX_EXPANDED_BYTES", 10000)
    monkeypatch.setattr(formats, "MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(DomainError) as error:
        formats.parse(payload, "CSV")
    assert error.value.code == "SOURCE_TOO_LARGE"


def test_normalized_key_repetition_and_archive_provenance_are_bounded(monkeypatch):
    monkeypatch.setattr(formats, "MAX_NORMALIZED_BYTES", 240)
    # Tiny raw CSV expands through repeated long JSON keys.
    with pytest.raises(DomainError) as error:
        formats.parse(("long_column_name_" * 4 + "\n" + "v\n" * 10).encode(), "CSV")
    assert error.value.code == "SOURCE_TOO_LARGE"
    with pytest.raises(DomainError):
        formats.parse(
            zipped([("a_very_long_source_member_name.csv", b"a\n1\n2\n3\n4\n")]), "CSV"
        )


def test_valid_flat_csv_json_and_workbook_positive_controls():
    book = Workbook()
    book.active.append(["code", "value"])
    book.active.append(["001", "=1+1"])
    out = io.BytesIO()
    book.save(out)
    for body, fmt in [
        (out.getvalue(), "XLSX"),
        (zipped([("table.xlsx", out.getvalue())]), "CSV"),
    ]:
        rows, _ = formats.parse(body, fmt)
        assert rows[0]["code"] == "001"
        assert rows[0]["value"] == "=1+1"
    rows, schema = formats.parse(
        zipped([("a.csv", b"a\n1\n"), ("b.json", b'[{"a":"2"}]')]), "CSV"
    )
    assert [r["a"] for r in rows] == ["1", "2"]
    assert len(schema["archiveMembers"]) == 2


def test_workbooks_also_enforce_actual_expansion_and_reject_embedded_zip(monkeypatch):
    book = Workbook()
    book.active.append(["a"])
    book.active.append(["1"])
    out = io.BytesIO()
    book.save(out)
    with zipfile.ZipFile(io.BytesIO(out.getvalue())) as archive:
        entries = [(m.filename, archive.read(m)) for m in archive.infolist()]
    with pytest.raises(DomainError) as error:
        formats.parse(zipped(entries + [("xl/media/data.bin", zipped([]))]), "XLSX")
    assert error.value.code == "NESTED_ARCHIVE"
    monkeypatch.setattr(formats, "MAX_EXPANDED_BYTES", 100)
    with pytest.raises(DomainError) as error:
        formats.parse(out.getvalue(), "XLSX")
    assert error.value.code == "SOURCE_TOO_LARGE"


def test_default_normalized_limit_rejects_small_csv_with_repeated_large_keys():
    with pytest.raises(DomainError) as error:
        formats.parse(("x" * 1000 + "\n" + "v\n" * 9000).encode(), "CSV")
    assert error.value.code == "SOURCE_TOO_LARGE"
