from datetime import date, timedelta

import pytest

from mcp_open_data_hk.curated.official_acceptance import BASELINE_SHA256, reconcile


def inventory():
    rows = []
    for n in range(94):
        week = (date(2024, 12, 30) + timedelta(weeks=n)).strftime("%Y%m%d")
        for register in "LF":
            key = f"https://www.cr.gov.hk/docs/wrpt/RNC063/RNC063{register}_{week}.csv"
            rows.append(
                {
                    "sourceKey": key,
                    "captureId": key,
                    "publishedCaptureId": key,
                    "valid": True,
                    "transformSha256": "a" * 64,
                    "rawSha256": "b" * 64,
                    "storedRows": 0,
                    "receipt": {
                        "sourceUrl": key,
                        "independentXlsVerified": True,
                        "verificationSha256": "c" * 64,
                        "rowCount": 0,
                        "sha256": "b" * 64,
                    },
                }
            )
    return {
        "sha256": BASELINE_SHA256,
        "sourceKeys": [r["sourceKey"] for r in rows],
    }, rows


def test_all_exact_keys_required_and_publication_is_separate_from_live_acceptance():
    baseline, rows = inventory()
    result = reconcile(baseline, rows, "official-test")
    assert result["inventoryPublicationPassed"]
    assert not result["restMcpBrowserDownloadAcceptancePassed"]
    assert not result["freshAcceptedBackupRestorePassed"]
    assert all(r["liveVerification"] == "pending" for r in result["cases"])
    # A total of 188 records cannot replace one missing original source key.
    rows[0] = dict(rows[0], sourceKey=rows[0]["sourceKey"] + ".new")
    result = reconcile(baseline, rows, "official-test")
    assert result["publishedQualifiedFiles"] == 187
    assert not result["inventoryPublicationPassed"]
    assert len(result["newSourceKeys"]) == 1


def test_staged_valid_inventory_does_not_pass_publication():
    baseline, rows = inventory()
    for row in rows[-20:]:
        row["publishedCaptureId"] = "prior-capture"
    result = reconcile(baseline, rows, "official-prior")
    assert result["qualifiedFiles"] == 188
    assert result["publishedQualifiedFiles"] == 168
    assert not result["inventoryPublicationPassed"]
    assert all(r["version"] is None for r in result["cases"] if not r["published"])


@pytest.mark.parametrize(
    "field,value", [("valid", False), ("storedRows", 1), ("rawSha256", "wrong")]
)
def test_rejects_unqualified_capture_or_row_count(field, value):
    baseline, rows = inventory()
    rows[0][field] = value
    result = reconcile(baseline, rows, "official-test")
    assert result["qualifiedFiles"] == 187
    assert result["issues"][0]["code"] == "SOURCE_CAPTURE_UNQUALIFIED"


def test_rejects_duplicate_keys_and_replaced_baseline():
    baseline, rows = inventory()
    with pytest.raises(ValueError, match="DUPLICATE_COMPANY_SOURCE_KEY"):
        reconcile(baseline, rows + rows[:1], "official-test")
    baseline["sourceKeys"][0] = baseline["sourceKeys"][1]
    with pytest.raises(ValueError, match="ORIGINAL_COMPANY_INVENTORY_REQUIRED"):
        reconcile(baseline, rows, "official-test")
