"""Synthetic semantics do not clear source access or output permission gates."""

import pytest
from mcp_open_data_hk.curated.official import SourceRejected
from mcp_open_data_hk.curated.qualified_fixtures import (
    dissolution_notice,
    sfc_corporate,
    hkex_disclosure,
)


def test_notice_proposal_absence_correction_and_identifier_namespaces():
    source = {
        "identifier": {"namespace": "cr:crn", "value": "0000123"},
        "noticeType": "proposed_striking_off",
        "issueDate": "2026-10-23",
        "eventDate": "2026-10-23",
    }
    proposal = dissolution_notice(source)
    assert (
        not proposal["effectiveDissolution"]
        and proposal["entity_id"] == "cr:crn:0000123"
    )
    assert dissolution_notice(dict(source, noticeType="dissolution"))[
        "effectiveDissolution"
    ]
    assert not dissolution_notice(
        dict(source, noticeType="dissolution", eventDate=None)
    )["effectiveDissolution"]
    correction = dissolution_notice(
        dict(source, noticeType="correction", supersedes="notice-A")
    )
    assert (
        correction["supersedes"] == "notice-A"
        and not correction["effectiveDissolution"]
    )
    with pytest.raises(SourceRejected):
        dissolution_notice(dict(source, noticeType="absent_from_search"))
    with pytest.raises(SourceRejected):
        dissolution_notice(
            dict(source, identifier={"namespace": "name", "value": "EXAMPLE"})
        )


def test_corporate_sfc_uses_exact_ce_and_limited_purpose():
    row = {
        "ceReference": "ABC001",
        "purpose": "licence_verification",
        "entityType": "corporate",
        "coveredThrough": "2026-10-23",
    }
    assert sfc_corporate(row)["entity_id"] == "sfc:ce:ABC001"
    for bad in [
        dict(row, purpose="marketing"),
        dict(row, entityType="individual"),
        dict(row, ceReference="ABC1"),
        dict(row, inferredBrn="0000123"),
        dict(row, formerExecutiveOfficers=[]),
    ]:
        with pytest.raises(SourceRejected):
            sfc_corporate(bad)


def test_di_replacement_is_not_an_additional_trade_or_current_holding():
    row = {
        "filingId": "F2",
        "issuerId": "00005",
        "stockCode": "00005",
        "replaces": "F1",
        "eventDate": "2026-10-20",
        "filedDate": "2026-10-22",
        "publishedDate": None,
    }
    parsed = hkex_disclosure(row)
    assert (
        parsed["filing_id"] == "hkex:di:F2"
        and parsed["issuer_id"] == "hkex:issuer:00005"
    )
    assert (
        parsed["eventDate"] != parsed["filedDate"] and parsed["publishedDate"] is None
    )
    assert (
        parsed["replaces"] == "F1"
        and "trade" not in parsed
        and "currentHolding" not in parsed
    )
    with pytest.raises(SourceRejected):
        hkex_disclosure(dict(row, replaces="F2"))
