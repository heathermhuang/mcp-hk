"""Invented HTML contracts; no source requests or vendor narrative fixtures."""

import pytest

from mcp_open_data_hk.curated.racing.profiles import (
    parse_profile,
    profile_url,
    profile_selection,
)
from mcp_open_data_hk.curated.racing.policy import RacingRejected


def page(kind="horse", source_id="HK_2026_K001", changed=None):
    if kind == "horse":
        name = "Fixture Horse (K001)"
        attrs = {
            "Country of Origin / Age": "NZ / 5",
            "Colour / Sex": "Bay / Gelding",
            "Current Rating": "60",
            "No. of 1-2-3-Starts*": "3-0-0-16",
            "Total Stakes*": "$2,028,550",
            "Import Date": "07/11/2024",
        }
        history = (
            "<table><tr>"
            + "".join(
                "<th>" + v + "</th>"
                for v in [
                    "Race Index",
                    "Pla.",
                    "Date",
                    "RC /Track/ Course",
                    "Dist.",
                    "Going",
                    "Class",
                    "Rating",
                    "Jockey",
                    "Video Replay",
                ]
            )
            + '</tr><tr><td><a href="/racing/information/English/Racing/LocalResults.aspx?racedate=2026/10/21&amp;racecourse=HV&amp;raceno=1">119</a></td><td>01</td><td>21/10/26</td><td>HV / Turf</td><td>1650</td><td>GOOD</td><td>4</td><td>60</td><td>Fixture</td><td>media excluded</td></tr></table>'
        )
    else:
        name = "Fixture Professional"
        attrs = {
            "No. of Wins": "26",
            "Total Rides": "118",
            "Win %": "22.03%",
            "Stakes won": "$33,526,675",
            "Nationality": "AUS",
        }
        history = ""
    if changed:
        attrs.update(changed)
    age = (
        ""
        if kind == "horse"
        else "<tr><td>Age: 43</td></tr><tr><td>26/27 Season Up to Race Meeting of 25/10/2026</td></tr>"
    )
    return (
        f'<html><title>Fixture profile</title><script>var {kind}id="{source_id}";</script><table><tr><td>{name}</td></tr>{age}'
        + "".join(
            "<tr><td>" + k + "</td><td>:</td><td>" + v + "</td></tr>"
            for k, v in attrs.items()
        )
        + "<tr><td>Email</td><td>:</td><td>private@example.invalid</td></tr></table>"
        + history
        + "</html>"
    )


def test_horse_attributes_dates_and_form_identity_preserve_source_semantics():
    result = parse_profile(
        page(), profile_url("horse", "HK_2026_K001"), "2026-10-26T00:00:00Z"
    )
    assert result["participantId"] == "hkjc:horse:HK_2026_K001"
    assert result["attributes"]["careerPlacings"]["value"] == {
        "wins": 3,
        "seconds": 0,
        "thirds": 0,
        "starts": 16,
    }
    assert result["attributes"]["totalStakes"]["value"] == "2028550"
    assert result["attributes"]["totalStakes"]["currency"] is None
    assert result["attributes"]["importDate"]["raw"] == "07/11/2024"
    assert result["attributes"]["importDate"]["value"] is None
    assert result["effectiveAt"] is None
    row = result["formHistory"][0]
    assert row["sourceAnnualIndex"] == "119"
    assert row["race"]["raceId"] == "hkjc:meeting:v1:2026-10-21:HV:01"
    assert row["race"]["date"] == "2026-10-21"
    assert "Video Replay" not in row["fields"]
    assert "private@example.invalid" not in str(result)
    assert result["coverage"]["completeCareerHistory"] is False


@pytest.mark.parametrize("kind,source_id", [("jockey", "PZ"), ("trainer", "NM")])
def test_professional_season_cutoff_is_separate_from_observation(kind, source_id):
    result = parse_profile(
        page(kind, source_id), profile_url(kind, source_id), "2026-10-26T00:00:00Z"
    )
    assert result["name"] == "Fixture Professional"
    assert result["attributes"]["winPercentage"]["value"] == "22.03"
    assert result["statisticsCutoff"]["value"] == "2026-10-25"
    assert result["observedAt"].startswith("2026-10-26")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/en-us/local/information/horse?horseid=HK_2026_K001",
        "https://racing.hkjc.com/en-us/local/information/horse?horseid=HK_2026_K001&horseid=HK_2026_K002",
        "https://racing.hkjc.com/en-us/local/information/horse?horseid=HK_2026_K001&HorseId=HK_2026_K002",
        "https://racing.hkjc.com/en-us/local/information/jockeyprofile?jockeyid=PZ&Season=all",
        "https://user:password@racing.hkjc.com/en-us/local/information/horse?horseid=HK_2026_K001",
    ],
)
def test_profile_routes_are_fixed_and_exact(url):
    with pytest.raises(RacingRejected):
        profile_selection(url)


def test_wrong_identity_schema_missing_and_impossible_counts_cannot_become_profile():
    url = profile_url("horse", "HK_2026_K001")
    for body in [
        page().replace("HK_2026_K001", "HK_2026_K002"),
        "<html>login</html>",
        page(changed={"No. of 1-2-3-Starts*": "30-0-0-16"}),
    ]:
        with pytest.raises(RacingRejected):
            parse_profile(body, url, "2026-10-26T00:00:00Z")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("二千零二十一", "2021"),
        ("一百三十六", "136"),
        ("十七點八", "17.8"),
        ("九點八", "9.8"),
        ("零", "0"),
    ],
)
def test_chinese_source_numerals_are_lossless(raw, expected):
    from mcp_open_data_hk.curated.racing.profiles import chinese_number

    assert chinese_number(raw) == expected


def test_bilingual_merge_rejects_differing_professional_facts():
    from mcp_open_data_hk.curated.racing.profiles import merge_profiles

    en = page("jockey", "PZ")
    zh = (
        en.replace("Age: 43", "年齡： 43歲")
        .replace("No. of Wins", "冠")
        .replace("Win %", "勝出率")
        .replace("Total Rides", "總出賽次數")
        .replace("Stakes won", "所贏獎金")
        .replace("Nationality", "國籍")
        .replace("26/27 Season Up to Race Meeting of", "26/27 馬季 截至賽事日:")
    )
    left = parse_profile(en, profile_url("jockey", "PZ"), "2026-10-26T00:00:00Z")
    right = parse_profile(
        zh, profile_url("jockey", "PZ", "zh-hk"), "2026-10-26T00:00:01Z"
    )
    merged = merge_profiles(left, right)
    assert merged["statisticsCutoff"]["value"] == "2026-10-25"
    right["attributes"]["seasonWins"]["value"] = "27"
    with pytest.raises(RacingRejected, match="BILINGUAL_FACTS"):
        merge_profiles(left, right)
