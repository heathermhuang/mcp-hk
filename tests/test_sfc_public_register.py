"""Real-source protocol shape, fabricated source facts; no source requests in tests."""

import json
from datetime import datetime, timezone
import subprocess
import sys

import pytest

from mcp_open_data_hk.curated.sfc.contracts import Rejected
from mcp_open_data_hk.curated.sfc.public_register import parse_page
from sfc_support import source_page


def test_source_page_preserves_identity_bilingual_names_unknown_status_and_raw_dates():
    record = parse_page(source_page(), "zzz001", datetime.now(timezone.utc))
    assert (
        record.ce == "ZZZ001"
        and record.nameEn == "Fixture Corporation"
        and record.nameZhHant == "虛構測試法團"
    )
    assert (
        record.statusCode == "not_supplied"
        and record.activities[0].statusCode == "not_supplied"
    )
    assert record.activities[0].start.raw == "Apr 1, 2003 12:00:00 AM"
    assert record.activities[0].start.value == "2003-04-01"
    assert record.activities[0].end.value is None and record.sourceCutoff.value is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.replace(b"ZZZ001", b"ZZZ002"),
        lambda s: s.replace(b"Corporation", b"Individual"),
        lambda s: s.replace(b'"lcType": "C"', b'"lcType": "E"'),
        lambda s: s.replace(b'"actType": 1', b'"actType": 99'),
        lambda s: s.replace(b'"actType": 1', b'"actType": 1, "actType": 2'),
        lambda s: s.replace(b"12:00:00 AM", b"12:00:00 PM"),
        lambda s: s.replace(b"var licRecordData", b"var changedData"),
        lambda s: s.replace(b"</script>", b"var licRecordData = [];</script>"),
        lambda s: s.replace(b"Apr 1, 2003", b"Feb 30, 2024"),
        lambda s: s.replace(b'"isAmloLcCatDeem": false', b'"isAmloLcCatDeem": true'),
        lambda s: s.replace(b'"endDate": null', b'"endDate": "not-a-date"'),
    ],
)
def test_scope_identity_schema_and_date_drift_never_become_revocation(mutate):
    with pytest.raises(Rejected, match="SCHEMA_CHANGED"):
        parse_page(mutate(source_page()), "ZZZ001", datetime.now(timezone.utc))


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Login required</html>",
        b"<html>No record found</html>",
        source_page(packet=[]),
        b"x" * 262145,
    ],
)
def test_missing_denied_and_empty_source_states_are_not_empty_success(body):
    with pytest.raises(Rejected):
        parse_page(body, "ZZZ001", datetime.now(timezone.utc))


def test_multiple_periods_and_contacts_are_not_projected():
    packet = [
        {
            "lcType": "C",
            "phone": "12345",
            "regulatedActivity": {"actType": 9, "actDesc": "Fixture management"},
            "effectivePeriodList": [
                {"effectiveDate": "2020-01-01", "endDate": "2021-01-01"},
                {"effectiveDate": "2022-01-01", "endDate": None},
            ],
        }
    ]
    result = parse_page(
        source_page(packet=packet), "ZZZ001", datetime.now(timezone.utc)
    ).model_dump(mode="json")
    assert len(result["activities"]) == 2
    assert "phone" not in json.dumps(result) and "12345" not in json.dumps(result)


def test_operator_replay_runs_without_network_or_database(tmp_path):
    path = tmp_path / "source.html"
    path.write_bytes(source_page())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_open_data_hk.curated.sfc",
            "parse",
            "--html",
            str(path),
            "--ce",
            "ZZZ001",
            "--observed-at",
            "2026-10-25T00:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert (
        json.loads(result.stdout)["activities"][0]["start"]["raw"]
        == "Apr 1, 2003 12:00:00 AM"
    )
