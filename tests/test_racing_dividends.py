import pytest

from mcp_open_data_hk.curated.racing.public_results import Document
from mcp_open_data_hk.curated.racing.dividends import (
    parse_dividend_table,
    reconcile_dividends,
    validate_observation,
    qualified_pair,
)
from mcp_open_data_hk.curated.racing.policy import RacingRejected

RACE = "hkjc:race:v1:2026-07-15:HV:1"


def fixture(span="2", continuation=True):
    return (
        '<table><tr><td>Dividend</td></tr><tr><td>Pool</td><td>Winning Combination</td><td>Dividend (HK$)</td></tr><tr><td>WIN</td><td>03</td><td>111.00</td></tr><tr><td rowspan="'
        + span
        + '">PLACE</td><td>03</td><td>36.50</td></tr>'
        + ("<tr><td>11</td><td>1,020.50</td></tr>" if continuation else "")
        + "</table>"
    )


def test_explicit_rowspan_precision_combinations_and_unknown_stake_are_preserved():
    data = parse_dividend_table(Document(fixture()).root, RACE)
    assert data["state"] == "observed" and data["sourceRows"] == 3
    assert [q["pool"] for q in data["quotes"]] == ["WIN", "PLACE", "PLACE"]
    assert data["quotes"][0]["winningCombinationRaw"] == "03"
    assert (
        data["quotes"][2]["amount"] == "1020.50"
        and data["quotes"][2]["amountRaw"] == "1,020.50"
    )
    assert all(
        q["stakeAmount"] is None and q["stakeCurrency"] is None for q in data["quotes"]
    )
    assert not data["stakeNormalized"]


def test_missing_is_not_an_empty_or_zero_payout():
    assert (
        parse_dividend_table(
            Document("<table><tr><td>Unrelated</td></tr></table>").root, RACE
        )["quotes"]
        is None
    )
    assert qualified_pair(None, None) == {"state": "not_extracted", "quotes": None}


def test_round_pools_and_nonmonetary_links_are_reconciled_without_invented_amounts():
    en = (
        "<table><tr><td>Pool</td><td>Winning Combination</td><td>Dividend (HK$)</td></tr>"
        '<tr><td rowspan="2">8TH DOUBLE</td><td>03/3</td><td>1,059.50</td></tr>'
        "<tr><td>03/11</td><td>38.00</td></tr>"
        "<tr><td>2ND TREBLE</td><td>11/3/3</td><td>3,700.00</td></tr>"
        "<tr><td>4TH DOUBLE TRIO</td><td>1,3,11/3,4,11</td><td>28,159.00</td></tr>"
        "<tr><td>SIX UP</td><td>6/12/6/11/3/3</td><td>24,643,450.00</td></tr>"
        "<tr><td>JOCKEY CHALLENGE 1</td><td>Invented fixture name</td><td>Details</td></tr></table>"
    )
    zh = en
    for left, right in [
        ("Pool", "彩池"),
        ("Winning Combination", "勝出組合"),
        ("Dividend", "派彩"),
        ("8TH DOUBLE", "第八口孖寶"),
        ("2ND TREBLE", "第二口三寶"),
        ("4TH DOUBLE TRIO", "第四口孖T"),
        ("SIX UP", "六環彩"),
        ("JOCKEY CHALLENGE", "騎師王"),
        ("Details", "詳情"),
    ]:
        zh = zh.replace(left, right)
    left = parse_dividend_table(Document(en).root, RACE)
    right = parse_dividend_table(Document(zh).root, RACE, "zhHant")
    value = reconcile_dividends(left, right)
    assert value["sourceRows"] == 5 and value["tableDataRows"] == 6
    assert value["deferredNonmonetaryRows"] == 1
    assert value["quotes"][-1]["amount"] == "24643450.00"
    assert value["quotes"][0]["winningCombinationRaw"] == "03/3"
    assert "Invented fixture name" not in str(value)
    validate_observation(value, RACE)
    value["deferredNonmonetaryRows"] = 0
    with pytest.raises(RacingRejected, match="RECORD_INVALID"):
        validate_observation(value, RACE)
    right["deferredNonmonetaryRows"] = 0
    with pytest.raises(RacingRejected, match="BILINGUAL_MISMATCH"):
        reconcile_dividends(left, right)


@pytest.mark.parametrize(
    "text,code",
    [
        (fixture("1"), "ROWSPAN_UNQUALIFIED"),
        (fixture("4"), "ROWSPAN_UNQUALIFIED"),
        (fixture().replace("111.00", "REFUND"), "AMOUNT_UNQUALIFIED"),
        (fixture().replace("WIN</td>", "UNKNOWN POOL</td>"), "POOL_UNQUALIFIED"),
    ],
)
def test_unqualified_structures_are_not_silently_reinterpreted(text, code):
    with pytest.raises(RacingRejected, match=code):
        parse_dividend_table(Document(text).root, RACE)


def test_bilingual_reconciliation_preserves_source_precision_and_leading_zero_combinations():
    en = fixture()
    zh = (
        en.replace("Pool", "彩池")
        .replace("Winning Combination", "勝出組合")
        .replace("Dividend", "派彩")
        .replace("WIN", "獨贏")
        .replace("PLACE", "位置")
        .replace("111.00", "111.0")
    )
    first = parse_dividend_table(Document(en).root, RACE)
    second = parse_dividend_table(Document(zh).root, RACE, "zhHant")
    result = reconcile_dividends(first, second)
    assert result["quotes"][0]["sources"]["en"]["amount"] == "111.00"
    assert result["quotes"][0]["sources"]["zhHant"]["amount"] == "111.0"
    assert result["quotes"][0]["winningCombinationRaw"] == "03"
    with pytest.raises(RacingRejected, match="RECORD_INVALID"):
        validate_observation(result, RACE + ":OTHER")
    second["quotes"][0]["amount"] = "112.00"
    with pytest.raises(RacingRejected, match="BILINGUAL_MISMATCH"):
        reconcile_dividends(first, second)
    result["quotes"][0]["amount"] = "999.00"
    with pytest.raises(RacingRejected, match="RECORD_INVALID"):
        validate_observation(result, RACE)
