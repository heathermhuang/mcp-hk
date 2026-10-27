import pytest

from hkex_support import filing, window
from mcp_open_data_hk.curated.hkex.inventory import qualify


def proof():
    w = window().model_dump(mode="json")
    pages = [
        {
            "form": form,
            "pages": 1,
            "page": 1,
            "issuerId": "TEST_ISSUER",
            "channel": "dion",
            "dateBasis": "filed",
            "windowStart": w["start"],
            "windowEnd": w["end"],
            "snapshot": "same-source-snapshot",
            "captureSha256": "a" * 64,
            "sourceTotal": 1 if form == "1" else 0,
            "serials": ["TEST_001"] if form == "1" else [],
        }
        for form in ("1", "2", "3A", "3B", "3C", "3D")
    ]
    return (
        w,
        pages,
        [filing().model_dump(mode="json")],
        {
            "issuerId": "TEST_ISSUER",
            "permanentSourceIdentityQualified": True,
            "sourceEvidenceSha256": "b" * 64,
        },
    )


def test_exact_filing_window_closes_all_form_pages_and_retains_bounded_scope():
    w, pages, filings, identity = proof()
    result = qualify(w, pages, filings, identity=identity)
    assert result["pages"] == 6 and result["filingSerials"] == ["TEST_001"]
    assert (
        result["completeWithinQualifiedInventory"]
        and not result["widerIssuerOrHistoryCoverageQualified"]
    )
    with pytest.raises(ValueError, match="FORM_CHANNEL"):
        qualify(w, pages[:-1], filings, identity=identity)
    with pytest.raises(ValueError, match="FILING_DATE_WINDOW"):
        qualify(dict(w, basis="event"), pages, filings, identity=identity)
    with pytest.raises(ValueError, match="PERMANENT_ISSUER"):
        qualify(
            w,
            pages,
            filings,
            identity=dict(identity, permanentSourceIdentityQualified=False),
        )


def test_missing_pages_duplicate_serials_and_invented_filing_dates_fail_closed():
    w, pages, filings, identity = proof()
    pages[0]["pages"] = 2
    with pytest.raises(ValueError, match="PAGE_INVENTORY"):
        qualify(w, pages, filings, identity=identity)
    pages[0]["pages"] = 1
    pages[0]["serials"] *= 2
    pages[0]["sourceTotal"] = 2
    with pytest.raises(ValueError, match="TOTAL_OR_DUPLICATE"):
        qualify(w, pages, filings, identity=identity)
    w, pages, filings, identity = proof()
    filings[0]["filed_date"] = {
        "value": None,
        "precision": "unknown",
        "timezone": "unspecified",
    }
    with pytest.raises(ValueError, match="EXPLICIT_FILING_DATE"):
        qualify(w, pages, filings, identity=identity)


def test_missing_revision_target_cannot_pass_filing_inventory_closure():
    w, pages, filings, identity = proof()
    filings[0] = filing(
        "TEST_001", state="amendment", replaces="MISSING_PARENT"
    ).model_dump(mode="json")
    with pytest.raises(ValueError, match="CLOSURE_TARGET_MISSING"):
        qualify(w, pages, filings, identity=identity)
