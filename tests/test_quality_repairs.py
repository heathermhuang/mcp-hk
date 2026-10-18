import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.quality import freshness, review_interval, semantic_quality
from mcp_open_data_hk.refresh_queue import RefreshQueue
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


def test_no_record_message_is_zero_observations_not_a_fake_row():
    rows, schema = parse(b'{"message":"No record found"}', "JSON")
    assert rows == [] and schema["sourceContext"] == {"message": "No record found"}
    assert schema["sourceResult"] == "empty"
    assert parse(b'{"message":"A real announcement"}', "JSON")[0] == [
        {"message": "A real announcement"}
    ]
    with pytest.raises(DomainError):
        parse(b'{"success":false,"error":{"code":3}}', "JSON")


def test_validation_ttl_and_source_cadence_are_separate_from_semantic_quality():
    q = freshness(
        {"updateCadence": "Annually"}, {"isApi": False}, 100, now=100 + 2 * 86400
    )
    assert q["cacheExpired"] and not q["reviewOverdue"]
    assert q["validationAgeSeconds"] == 2 * 86400
    assert review_interval({"updateCadence": "Daily"}, {}) < review_interval(
        {"updateCadence": "Quarterly"}, {}
    )
    _, schema = parse(b"Title,,\nname,value,unit\na,2,persons\n", "CSV")
    q = semantic_quality(schema)
    assert q["hasPositionalColumns"] and not q["headerVerified"]
    assert q["semanticVerification"] == "not_performed"


def service_with_resources(tmp_path, held=0):
    s = Service(Store(str(tmp_path / "db.sqlite3")))
    dataset = {
        "id": "sample",
        "title": "Sample",
        "provider": "Department",
        "catalogue": "DATA.GOV.HK",
        "providerType": "government",
        "updateCadence": "Daily",
        "sourceUrl": "https://data.gov.hk/sample",
    }
    rows = [
        {
            "id": f"{i:032x}",
            "datasetId": "sample",
            "url": f"https://example.gov.hk/{i}.csv",
            "format": "CSV",
            "catalogue": "DATA.GOV.HK",
            "sourceUrl": "https://data.gov.hk/sample",
            "termsUrl": "https://data.gov.hk/terms",
        }
        for i in range(held + 2)
    ]
    s.resources.catalogue.publish([dataset], rows, {})
    with s.store.connect() as db:
        for r in rows[:held]:
            db.execute(
                "INSERT INTO resource_checks(id,status,reason,checked) VALUES (?,?,?,?)",
                (r["id"], "unsupported", "UNSUPPORTED_FORMAT", time.time()),
            )
    return s, rows


@pytest.mark.asyncio
async def test_due_queue_skips_held_ids_before_limit_and_preserves_backoff(tmp_path):
    s, rows = service_with_resources(tmp_path, held=80)
    calls = []

    async def inspect(rid, **kwargs):
        calls.append(rid)
        raise DomainError("SOURCE_TIMEOUT", "Unavailable")

    s.resources.schema = inspect
    queue = RefreshQueue(s.resources.catalogue)
    result = await queue.run(s.resources, 2, 10)
    assert result["processed"] == 2 and result["failed"] == 2
    assert set(calls) == {r["id"] for r in rows[80:]}
    assert (await queue.run(s.resources, 2, 10))["processed"] == 0
    state = s.resources.catalogue.coverage()["validationFreshness"]
    assert state["status"] == "active" and state["lastMaintenance"]["processed"] == 0


@pytest.mark.asyncio
async def test_successful_live_read_satisfies_review_deadline_without_rechecking(
    tmp_path,
):
    s, rows = service_with_resources(tmp_path)
    queue = RefreshQueue(s.resources.catalogue)
    queue.prepare()
    with s.store.connect() as db:
        for r in rows:
            db.execute(
                "INSERT INTO resource_checks(id,status,validated,checked) VALUES (?,?,?,?)",
                (r["id"], "queryable", time.time(), time.time()),
            )
    assert queue.due(100, time.time()) == []


@pytest.mark.asyncio
async def test_current_property_view_preserves_all_source_view_and_qualifications(
    tmp_path, monkeypatch
):
    from pathlib import Path

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "seehouse-building.json").read_text()
    )
    stamp = datetime.fromtimestamp(time.time() - 3600, timezone.utc).isoformat()
    for row in payload["listings"]:
        row["freshness"].update(observedAt=stamp, status="fresh", expiresAt=None)
        row["confidence"]["matchLevel"] = "building"
    payload["listings"][1]["confidence"]["matchLevel"] = "estate"

    async def upstream(*args):
        return payload

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", upstream)
    s = Service(Store(str(tmp_path / "props.sqlite3")))
    app = create_app(s)
    with TestClient(app) as http:
        all_rows = http.get(
            "/api/v1/properties/building", params={"buildingId": payload["id"]}
        ).json()["data"]
        current = http.get(
            "/api/v1/properties/building",
            params={"buildingId": payload["id"], "quality": "current"},
        ).json()["data"]
        assert len(all_rows["listings"]) == 2 and len(current["listings"]) == 1
        assert current["listingQuality"]["providerReturnedCount"] == 2
        assert all_rows["listings"][1]["quality"]["reasons"] == [
            "building_match_not_confirmed"
        ]
        assert not current["listings"][0]["quality"]["availabilityVerified"]
    async with Client(app.state.mcp) as client:
        assert (
            await client.call_tool(
                "hk_property_building",
                {"buildingId": payload["id"], "quality": "current"},
            )
        ).data["data"] == current


def test_failed_restaurant_refresh_is_degraded_even_with_a_retained_snapshot(tmp_path):
    s = Service(Store(str(tmp_path / "status.sqlite3")))
    row = {
        "id": "licence",
        "name": {"en": None, "zhHant": None},
        "address": {"en": "Source address", "zhHant": None},
        "latitude": 22.3,
        "longitude": 114.1,
    }
    s.store.publish("restaurants", [row], None)
    s.store.check("restaurants", "SOURCE_CHANGED_DURING_IMPORT")
    status = next(x for x in s.status()["sources"] if x["sourceId"] == "restaurants")
    assert status["refreshHealth"]["state"] == "degraded"
    assert status["refreshHealth"]["acceptedSnapshotRetained"]
    assert status["quality"]["sourceNamesMissingBothLanguages"] == 1
    assert status["quality"]["chineseAddressesMissing"] == 1


@pytest.mark.asyncio
async def test_restricted_never_validated_sources_cannot_starve_due_accepted_data(
    tmp_path,
):
    s, rows = service_with_resources(tmp_path)
    now = time.time()
    with s.store.connect() as db:
        db.execute(
            "INSERT INTO resource_checks(id,status,checked) VALUES (?,?,?)",
            (rows[0]["id"], "restricted", now - 172800),
        )
        db.execute(
            "INSERT INTO resource_checks(id,status,checked,validated) VALUES (?,?,?,?)",
            (rows[1]["id"], "queryable", now - 172800, now - 172800),
        )
    q = RefreshQueue(s.resources.catalogue)
    assert q.due(1, now)[0]["id"] == rows[1]["id"]


def test_compound_review_cadence_uses_fastest_update_and_closed_archives_are_not_live():
    assert (
        review_interval(
            {"updateCadence": "Monthly, except some columns updated annually"}, {}
        )
        == 7 * 86400
    )
    assert (
        review_interval({"updateCadence": "Quarterly and annually"}, {}) == 21 * 86400
    )
    assert (
        review_interval(
            {
                "updateCadence": "Only the hourly API of the period from July 1999 to December 2013 is available"
            },
            {},
        )
        == 90 * 86400
    )
    assert review_interval({"updateCadence": "Hourly"}, {}) == 300
