"""Real-source parser fixtures and fail-closed ingestion boundaries."""

import csv
import io
import json
from pathlib import Path

import pytest

from mcp_open_data_hk.curated.official import (
    SourceRejected,
    address,
    discover,
    lenders,
    weekly,
    verify_xls,
)

FIX = Path(__file__).parent / "fixtures" / "official"


def fixture(name):
    return (FIX / name).read_bytes()


def rewrite(body, change):
    rows = list(csv.DictReader(io.StringIO(body.decode())))
    fields = list(rows[0])
    change(rows)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def test_weekly_preserves_aliases_combined_event_and_namespace():
    rows = weekly(fixture("weekly-foreign.csv"), "foreign", "20261012")
    assert rows[0]["entity_id"] == rows[1]["entity_id"] == "cr:foreign:73101900"
    assert rows[0]["name1"] != rows[1]["name1"]
    assert rows[0]["events"][0]["type"] == "name_change"
    body = rewrite(
        fixture("weekly-local.csv"),
        lambda rows: rows[0].update(
            {
                "BR Number": "00001234",
                "Current Company Name in English": '=RAW "Limited"',
            }
        ),
    )
    row = weekly(body, "local", "20261012")[0]
    assert row["identifier"]["value"] == "00001234"
    assert row["entity_id"] == "cr:local:00001234"
    assert row["name1"] == '=RAW "Limited"'
    assert row["events"][0] == {
        "type": "incorporation_or_redomiciliation",
        "date": "2026-10-12",
        "dateRaw": "12-10-2026",
        "precision": "day",
    }
    old = body.replace(
        b"Date of Incorporation / Re-domiciliation Date", b"Date of Incorporation"
    )
    assert weekly(old, "local", "20261012")[0]["events"][0]["type"] == "incorporation"


@pytest.mark.parametrize("file", ["ml_licensees", "ml_list1", "ml_list2", "ml_list3"])
def test_money_lender_registers_do_not_invent_brn(file):
    rows = lenders(fixture(file + ".csv"), file)
    assert rows[0]["coverageEnd"] == "2026-09-30"
    assert rows[0]["identifier"]["namespace"] == "cr:mlr"
    assert "BRN" not in rows[0]["raw"]


@pytest.mark.parametrize("scope,brn", [("local", "81363340"), ("foreign", "81362310")])
def test_exact_address_identity_and_missing_are_distinct(scope, brn):
    row = address(fixture(scope + ".json"), scope, brn)[0]
    assert row["address"] and row["effectiveFrom"] is None
    with pytest.raises(SourceRejected):
        address(fixture(scope + ".json"), scope, "00000001")
    with pytest.raises(SourceRejected):
        address(b"[]", scope, brn)
    changed = json.loads(fixture(scope + ".json"))
    changed[0]["Brn"] = int(brn)
    with pytest.raises(SourceRejected):
        address(json.dumps(changed).encode(), scope, brn)


def test_partial_empty_out_of_week_and_schema_drift_fail_closed():
    body = fixture("weekly-local.csv")
    for bad in [
        b"",
        body[:-8],
        body.replace(b"BR Number", b"CR Number"),
        body.replace(b"12-10-2026", b"11-10-2026"),
        body.split(b"\n", 1)[0] + b"\n",
    ]:
        with pytest.raises(SourceRejected):
            weekly(bad, "local", "20261012")


def test_catalogue_requires_complete_local_foreign_pairs():
    base = "https://www.cr.gov.hk/docs/wrpt/RNC063/RNC063"
    body = (base + "L_20261012.csv " + base + "F_20261012.csv").encode()
    assert len(discover(body)) == 2
    with pytest.raises(SourceRejected):
        discover(body.split(b" ")[0])


def test_independent_xls_rejects_row_mismatch(monkeypatch):
    import xlrd

    body = fixture("ml_list1.csv")
    fields = next(csv.reader(io.StringIO(body.decode())))

    class Sheet:
        nrows = 1

        def row_values(self, index):
            return fields

    class Book:
        def sheet_by_index(self, index):
            return Sheet()

    monkeypatch.setattr(xlrd, "open_workbook", lambda **kwargs: Book())
    with pytest.raises(SourceRejected, match="CSV_XLS_ROWS_DIFFER"):
        verify_xls(body, b"independent truncated sheet")


def test_collector_limits_and_upstream_failures_have_bounded_codes():
    import httpx
    from mcp_open_data_hk.curated.official_ingest import Collector

    collector = Collector()
    collector.client.close()
    collector.client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(429))
    )
    try:
        with pytest.raises(SourceRejected, match="SOURCE_HTTP_429"):
            collector.get("https://www.cr.gov.hk/datagovhk/psi/ml_licensees.csv")
        assert collector.checks[0]["httpStatus"] == 429
        collector.requests = 48
        with pytest.raises(SourceRejected, match="RUN_REQUEST_OR_TIME_BUDGET"):
            collector.get("https://www.cr.gov.hk/datagovhk/psi/ml_licensees.csv")
        assert len(collector.checks) == 1
    finally:
        collector.close()


@pytest.mark.parametrize(
    "status,payload,content_type,route,expected",
    [
        (
            400,
            {"status": 400, "message": "No result found."},
            "application/json",
            "foreign",
            "SOURCE_NO_MATCH",
        ),
        (
            400,
            {"status": 400, "message": "No result found."},
            "application/json; charset=utf-8",
            "local",
            "SOURCE_NO_MATCH",
        ),
        (
            400,
            {"status": 400, "message": "Invalid query"},
            "application/json",
            "foreign",
            "SOURCE_HTTP_400",
        ),
        (
            400,
            {"status": "400", "message": "No result found."},
            "application/json",
            "foreign",
            "SOURCE_HTTP_400",
        ),
        (
            400,
            {"status": 400, "message": "No result found.", "denied": True},
            "application/json",
            "foreign",
            "SOURCE_HTTP_400",
        ),
        (
            403,
            {"status": 400, "message": "No result found."},
            "application/json",
            "foreign",
            "SOURCE_HTTP_403",
        ),
        (
            400,
            {"status": 400, "message": "No result found."},
            "text/html",
            "foreign",
            "SOURCE_HTTP_400",
        ),
        (
            400,
            {"status": 400, "message": "No result found."},
            "application/json",
            "other",
            "SOURCE_HTTP_400",
        ),
    ],
)
def test_registry_no_match_requires_exact_error_and_qualified_route(
    status, payload, content_type, route, expected
):
    import httpx
    from mcp_open_data_hk.curated.official_ingest import Collector
    from mcp_open_data_hk.curated.official import digest

    body = json.dumps(payload).encode()
    collector = Collector()
    collector.client.close()
    collector.client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                status, content=body, headers={"content-type": content_type}
            )
        )
    )
    params = {
        "query[0][key1]": "Brn",
        "query[0][key2]": "equal",
        "query[0][key3]": "00562995",
    }
    try:
        with pytest.raises(SourceRejected, match="^" + expected + "$"):
            collector.get(
                f"https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/{route}/search",
                params,
            )
        assert collector.checks[0]["sha256"] == digest(body)
        assert collector.checks[0]["bytes"] == len(body)
        assert collector.checks[0]["outcome"] == expected
    finally:
        collector.close()


def test_registry_error_body_is_bounded_and_invalid_json_cannot_match():
    import httpx
    from mcp_open_data_hk.curated.official_ingest import Collector

    url = "https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/foreign/search"
    params = {
        "query[0][key1]": "Brn",
        "query[0][key2]": "equal",
        "query[0][key3]": "00562995",
    }
    for body in [b'{"status":400,"message":"No result found."} garbage', b"x" * 8192]:
        collector = Collector()
        collector.client.close()
        collector.client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    400, content=body, headers={"content-type": "application/json"}
                )
            )
        )
        try:
            with pytest.raises(SourceRejected, match="SOURCE_HTTP_400"):
                collector.get(url, params)
            assert collector.checks[0]["bytes"] <= 4096
            assert collector.checks[0]["bodyTruncated"] == (len(body) > 4096)
        finally:
            collector.close()


def test_xls_quote_prefix_requires_explicit_metadata_and_preserves_csv(monkeypatch):
    import xlrd
    from types import SimpleNamespace

    body = fixture("weekly-local.csv")
    body = rewrite(
        body,
        lambda rows: rows[0].update(
            {"Current Company Name in English": "'Plutus Example Limited"}
        ),
    )
    fields, raw = __import__(
        "mcp_open_data_hk.curated.official", fromlist=["csv_rows"]
    ).csv_rows(body)

    class Sheet:
        nrows = len(raw) + 1
        extra = ["", ""]

        def row_values(self, index):
            return (
                fields if index == 0 else [raw[index - 1][f] for f in fields]
            ) + self.extra

        def cell(self, index, col):
            value = raw[index - 1][fields[col]]
            if index == 1 and col == 1:
                value = value[1:]
            return SimpleNamespace(
                value=value,
                ctype=xlrd.XL_CELL_TEXT,
                xf_index=1 if index == 1 and col == 1 else 0,
            )

    class Book:
        datemode = 0
        xf_list = [
            SimpleNamespace(lotus_123_prefix=0),
            SimpleNamespace(lotus_123_prefix=1),
        ]

        def sheet_by_index(self, index):
            return Sheet()

    book = Book()
    monkeypatch.setattr(xlrd, "open_workbook", lambda **kwargs: book)
    assert verify_xls(body, b"fixture") == len(raw)
    evidence = {}
    assert verify_xls(body, b"fixture", evidence) == len(raw)
    assert evidence["excelQuotePrefixCells"] == 1 and evidence["sourceCsvTextPreserved"]
    assert weekly(body, "local", "20261012")[0]["name1"] == "'Plutus Example Limited"
    book.xf_list[1].lotus_123_prefix = 0
    with pytest.raises(SourceRejected, match="CSV_XLS_ROWS_DIFFER"):
        verify_xls(body, b"fixture")
    book.xf_list[1].lotus_123_prefix = 1
    different = body.replace(b"Plutus Example Limited", b"Plutus Different Limited")
    with pytest.raises(SourceRejected, match="CSV_XLS_ROWS_DIFFER"):
        verify_xls(different, b"fixture")
    Sheet.extra = ["unexpected source data"]
    with pytest.raises(SourceRejected, match="XLS_SCHEMA_CHANGED"):
        verify_xls(body, b"fixture")
    original_row_values = Sheet.row_values
    monkeypatch.setattr(
        Sheet,
        "row_values",
        lambda self, index: (
            fields + [""] if index == 0 else original_row_values(self, index)
        ),
    )
    with pytest.raises(SourceRejected, match="XLS_EXTRA_SOURCE_COLUMNS"):
        verify_xls(body, b"fixture")


def test_reparse_receipt_retains_original_source_observation_time():
    from mcp_open_data_hk.curated.official import capture_receipt

    stamp = "2026-10-24T05:44:00+00:00"
    receipt = capture_receipt(
        "https://www.cr.gov.hk/test", b"source", {}, [], fetched_at=stamp
    )
    assert receipt["fetchedAt"] == stamp
