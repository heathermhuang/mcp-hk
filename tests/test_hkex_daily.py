import pytest
from datetime import date

from hkex_daily_support import DAY, menu, report
from mcp_open_data_hk.curated.hkex_daily.parser import (
    parse_menu,
    parse_report,
    Document,
    MAX_BODY,
)
from mcp_open_data_hk.hkex_daily import DailyQuery


@pytest.mark.parametrize("category", [1, 2, 3, 4])
def test_summary_categories_preserve_precision_dates_and_scope(category):
    r = parse_report(report(category), DAY, category)
    row = r["rows"][0]
    assert row["stock_code"] == "00005" and row["issuer_id"] == "hkex:issuer:100"
    assert row["interests"][0]["shares"] == "9007199254740993.00000001"
    assert (
        row["interests"][1]["position"] == "short"
        and row["interests"][1]["shares"] == "0"
    )
    assert row["event_date"] == row["summary_date"] == "2026-10-23"
    assert row["filed_date"] is row["published_timestamp"] is None
    assert row["detail_scope"] == "published_daily_summary_only"
    assert row["associated_corporation"] == (
        "Synthetic associated corporation" if category >= 3 else None
    )


def test_amendment_reference_does_not_become_a_second_disclosure():
    r = parse_report(report(2, amendment=True), DAY, 2)
    assert r["count"] == 1 and r["rows"][0]["revision"]["amends"] == "DA20261022E00001"


@pytest.mark.parametrize("category", [1, 2, 3, 4])
def test_structured_empty_report_is_distinct_from_error_or_login(category):
    assert parse_report(report(category, empty=True), DAY, category)["count"] == 0
    with pytest.raises(ValueError):
        parse_report(
            b"<html><body>Temporarily unavailable</body></html>", DAY, category
        )
    with pytest.raises(ValueError):
        parse_report(
            b"<html><body>Sign in Date: 23/10/2026</body></html>", DAY, category
        )


def test_source_date_identity_schema_and_complete_body_fail_closed():
    with pytest.raises(ValueError, match="DATE_MISMATCH"):
        parse_report(report(), date(2026, 10, 22), 1)
    with pytest.raises(ValueError, match="STOCK_IDENTITY"):
        parse_report(report().replace(b">00005<", b">00006<"), DAY, 1)
    with pytest.raises(ValueError, match="UNRECOGNIZED"):
        parse_report(
            report().replace(
                b'<a href="/di/NSForm2.aspx', b'<a href="/wrong/NSForm2.aspx'
            ),
            DAY,
            1,
        )
    with pytest.raises(ValueError, match="INCOMPLETE"):
        parse_report(report()[:-7], DAY, 1)
    with pytest.raises(ValueError, match="BODY_LIMIT"):
        Document(b"x" * (MAX_BODY + 1))
    with pytest.raises(ValueError, match="SERIAL"):
        parse_report(report().replace(b"CS20261023E00001", b"XX20261023E00001"), DAY, 1)


def test_menu_requires_all_four_categories_for_one_real_date():
    assert parse_menu(menu()) == DAY
    with pytest.raises(ValueError):
        parse_menu(menu().replace(b"C4.htm", b"C2.htm"))
    with pytest.raises(ValueError):
        parse_menu(menu().replace(b"20261023C4", b"20261022C4"))


def test_public_query_bounds():
    from pydantic import ValidationError

    assert DailyQuery(stockCode="5").stockCode == "5"
    for fields in (
        {"stockCode": "000005"},
        {"start": "2026-10-01"},
        {"start": "2026-10-01", "end": "2026-12-01"},
        {"limit": 101},
    ):
        with pytest.raises(ValidationError):
            DailyQuery(**fields)
