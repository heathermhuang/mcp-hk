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
