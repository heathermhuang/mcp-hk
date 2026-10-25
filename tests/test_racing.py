"""Offline racing semantics and fail-closed public surface contracts."""

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import httpx
import pytest

from racing_support import source_policy, ROUTE, bundle
from mcp_open_data_hk.curated.racing.policy import RacingRejected, checksum, require
from mcp_open_data_hk.curated.racing.normalize import (
    participant,
    race,
    result_row,
    reconcile,
    dividend,
    sectional,
)
from mcp_open_data_hk.curated.racing.export import build_export
from mcp_open_data_hk.curated.racing.validate import validate_bundle
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk import racing


def row(**changes):
    return {
        "horseId": "HK_2025_001",
        "horseNumber": "01",
        "draw": "09",
        "placing": "1",
        "time": "1:09.23",
        "weightLb": "120.5",
        "claimLb": "2",
        "marginRaw": "--",
        **changes,
    }


def test_identity_units_revisions_and_reordering():
    rid = race("2026-01-01", "HV", 1)
    record = result_row(row(), rid)
    assert record["horseNumber"] == "01" and record["draw"] == "09"
    assert record["timeSeconds"] == "69.23" and record["weightLb"] == "120.5"
    assert record == result_row(dict(reversed(list(row().items()))), rid)
    corrected = result_row(row(placing="2"), rid)
    assert (
        corrected["factId"] == record["factId"]
        and corrected["revision"] != record["revision"]
    )
    assert participant("horse", "001") != participant("jockey", "001")
    assert race("2026-01-01", "ST", 1) != rid


@pytest.mark.parametrize("code", ["WV", "WD", "UR", "DNF", "DISQ", "PU", "FE", "WX"])
def test_non_finishers_are_not_zero(code):
    result = result_row(row(placing=code, time=None), "synthetic-race")
    assert result["placing"] is None and result["timeSeconds"] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"placing": "??"},
        {"time": "1:89.23"},
        {"weightLb": 120.5},
        {"time": "--", "newColumn": "drift"},
        {"placing": "WV"},
    ],
)
def test_drift_and_float_rejected(changes):
    with pytest.raises(RacingRejected):
        result_row(row(**changes), "race")


def test_declared_inventory_and_dead_heat():
    rows = [
        result_row(row(placing="1 DH"), "r"),
        result_row(row(horseId="002", placing="1 DH"), "r"),
        result_row(row(horseId="003", placing="WV", time=None), "r"),
    ]
    declared = [record["participantId"] for record in rows]
    assert reconcile(["r"], {"r": declared}, {"r": rows})[0]["declared"] == 3
    with pytest.raises(RacingRejected, match="DECLARED_RUNNER_GAP"):
        reconcile(["r"], {"r": declared}, {"r": rows[:2]})
    with pytest.raises(RacingRejected, match="DEAD_HEAT"):
        reconcile(["r"], {"r": declared[:1]}, {"r": rows[:1]})


def test_policy_modes_expiry_routes_revocation_and_pin():
    policy = source_policy()
    pin = checksum(policy)
    require(policy, pin, "results", "collect", route=ROUTE)
    with pytest.raises(RacingRejected, match="INACTIVE"):
        require(policy, "0" * 64, "results", "collect")
    with pytest.raises(RacingRejected, match="INACTIVE"):
        require(
            policy,
            pin,
            "results",
            "collect",
            now=datetime(2100, 1, 1, tzinfo=timezone.utc),
        )
    for state in ("unknown", "denied"):
        policy["families"]["results"]["modes"]["export"] = state
        with pytest.raises(RacingRejected, match="UNQUALIFIED"):
            require(policy, checksum(policy), "results", "export")
    with pytest.raises(RacingRejected, match="LOCATION"):
        require(
            policy, checksum(policy), "results", "collect", route="https://evil.test/"
        )
    policy["state"] = "revoked"
    with pytest.raises(RacingRejected, match="INACTIVE"):
        require(policy, checksum(policy), "results", "rest")


def test_independent_coverage_and_source_ids():
    manifest, tables = bundle(checksum(source_policy()))
    assert validate_bundle(manifest, tables)
    tables["results"].pop()
    with pytest.raises(RacingRejected, match="INVENTORY"):
        validate_bundle(manifest, tables)


def test_dividends_and_sectionals():
    base = {
        "semantics": "unordered",
        "currency": "HKD",
        "status": "payout",
        "combination": ["09", "01"],
        "amount": "123.40",
        "stakeHkd": "10",
    }
    assert dividend(base)["combination"] == ["01", "09"]
    assert dividend(dict(base, semantics="ordered"))["combination"] == ["09", "01"]
    with pytest.raises(RacingRejected):
        dividend(dict(base, combination=["F"]))
    assert (
        sectional(
            {
                "kind": "runner",
                "unit": "seconds",
                "segment": 1,
                "distanceM": 400,
                "seconds": "23.40",
            }
        )["seconds"]
        == "23.40"
    )


def test_export_exactness_manifest_safe_paths_and_denial():
    policy = source_policy()
    rows = [{"id": "001", "name": "=1+1", "amount": "0.10"}]
    data, manifest = build_export(
        policy,
        checksum(policy),
        "results",
        "v1",
        rows,
        fields=["id", "name", "amount"],
        cutoff="2026-01-01",
    )
    assert (
        data
        == build_export(
            policy,
            checksum(policy),
            "results",
            "v1",
            rows,
            fields=["id", "name", "amount"],
            cutoff="2026-01-01",
        )[0]
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert json.loads(archive.read("records.json")) == rows
        assert "'=1+1" in archive.read("records.csv").decode("utf-8-sig")
        for name, info in manifest["files"].items():
            assert (
                "/" not in name
                and hashlib.sha256(archive.read(name)).hexdigest() == info["sha256"]
            )
    policy["families"]["results"]["modes"]["export"] = "denied"
    with pytest.raises(RacingRejected):
        build_export(
            policy,
            checksum(policy),
            "results",
            "v1",
            rows,
            fields=["id", "name", "amount"],
            cutoff=None,
        )


@pytest.mark.asyncio
async def test_public_rest_mcp_gate_no_traffic_or_fake_empty(tmp_path):
    service = Service(Store(str(tmp_path / "racing.sqlite")))
    app = create_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as client:
        status = await client.get("/api/v1/racing/status")
        assert status.json() == racing.status()
        for route in (
            "races",
            "races/a/results",
            "participants/a",
            "observations",
            "exports",
        ):
            response = await client.get(
                "/api/v1/racing/" + route + "?enabled=true&url=https://evil.test"
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "RACING_SOURCE_UNQUALIFIED"
        schema = (await client.get("/openapi.json")).json()
        assert "/api/v1/racing/status" in schema["paths"]
        assert "/api/v1/racing/races" not in schema["paths"]
        tools = await app.state.mcp.get_tools()
        assert "hk_racing_status" in tools and "hk_racing_search" not in tools
        assert tools["hk_racing_status"].fn() == racing.status()


@pytest.mark.parametrize("chinese", [False, True])
def test_bilingual_contract_html_column_reorder_and_entity_text(chinese):
    from html import escape
    from mcp_open_data_hk.curated.racing.parser import HEADERS, parse_contract_html

    labels = list(HEADERS)[1::2] if chinese else list(HEADERS)[::2]
    keys = [HEADERS[label] for label in labels]
    values = row()
    # Independent expected facts above; table builder does not normalize them.
    html = (
        "<table><tr>"
        + "".join("<th>" + escape(label) + "</th>" for label in reversed(labels))
        + "</tr><tr>"
        + "".join("<td>" + escape(values[key]) + "</td>" for key in reversed(keys))
        + "</tr></table>"
    )
    result = parse_contract_html(html, "synthetic-race")
    assert result[0]["participantId"] == "hkjc:horse:HK_2025_001"
    assert result[0]["timeSeconds"] == "69.23" and result[0]["horseNumber"] == "01"
    with pytest.raises(RacingRejected, match="DRIFT"):
        parse_contract_html(html.replace(labels[0], "unknown field"), "r")


def test_prospective_series_start_gap_and_capacity():
    from mcp_open_data_hk.curated.racing.series import series_receipt, capacity

    rows = [
        {
            "seriesId": "series-001",
            "selection": "01",
            "sequence": number,
            "kind": "odds",
            "state": "open",
            "value": "1.10",
            "rawUnit": "decimal odds",
            "sourceAt": None,
            "observedAt": stamp,
        }
        for number, stamp in enumerate(
            ("2026-10-25T00:00:00Z", "2026-10-25T00:01:00Z", "2026-10-25T00:04:00Z")
        )
    ]
    receipt = series_receipt(rows, 60, end="2026-10-25T00:04:00Z")
    assert receipt["actualStart"] == "2026-10-25T00:00:00+00:00"
    assert receipt["measuredIntervals"][:2] == [60.0, 180.0]
    assert receipt["gaps"][0]["missingSamplesAtLeast"] == 2
    assert series_receipt([], 60, end="2026-10-25T00:04:00Z")["actualStart"] is None
    assert capacity(
        samples_per_day=60,
        markets=1,
        selections=14,
        bytes_per_row=400,
        retention_days=30,
    )["withinInitialOneGiB"]
    assert not capacity(
        samples_per_day=86400,
        markets=10,
        selections=100,
        bytes_per_row=400,
        retention_days=365,
    )["withinInitialOneGiB"]
