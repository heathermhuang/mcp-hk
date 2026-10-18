import json
import time
import asyncio
from collections import Counter
from urllib.parse import urlsplit
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


def service_with_resources(tmp_path, held=0, count=2, hosts=1):
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
            "url": f"https://source{i % hosts}.gov.hk/{i}.csv",
            "format": "CSV",
            "catalogue": "DATA.GOV.HK",
            "sourceUrl": "https://data.gov.hk/sample",
            "termsUrl": "https://data.gov.hk/terms",
        }
        for i in range(held + count)
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


def test_review_capacity_rejects_the_production_underprovision_and_future_growth():
    from mcp_open_data_hk.review_config import capacity

    required = 29569.1  # Confirmed production interval histogram, 2026-10-18.
    assert capacity(required, budget=2400)["status"] == "insufficient"
    current = capacity(required)
    assert current["status"] == "sufficient" and current["headroomRatio"] >= 1.2
    assert capacity(100000)["status"] == "insufficient"


def test_variant_review_lookup_uses_index_and_preserves_latest_and_pruning(tmp_path):
    s, rows = service_with_resources(tmp_path)
    rid = rows[0]["id"]
    for index in range(65):
        schema = {
            "fields": [{"name": "id", "types": ["string"]}],
            "recordPath": f"rows{index}",
        }
        s.resources.catalogue.accept(
            rid, f"variant-{index}", [{"id": "source"}], schema, f"hash-{index}", {}
        )
    q = RefreshQueue(s.resources.catalogue)
    assert q.selectors(rid) == {"record_path": "rows64"}
    with s.store.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM resource_variants WHERE resource=?", (rid,)
            ).fetchone()[0]
            == 50
        )
        plan = [
            r[3]
            for r in db.execute(
                "EXPLAIN QUERY PLAN SELECT schema_json FROM resource_variants WHERE resource=? AND schema_json IS NOT NULL ORDER BY validated DESC LIMIT 1",
                (rid,),
            )
        ]
        assert any("SEARCH resource_variants" in detail for detail in plan)
        assert not any("SCAN resource_variants" in detail for detail in plan)


@pytest.mark.asyncio
async def test_hosted_recovery_limits_reject_uncheckpointed_long_calls(tmp_path):
    s, _ = service_with_resources(tmp_path)
    with pytest.raises(ValueError):
        await RefreshQueue(s.resources.catalogue).run(s.resources, 256, 600)


@pytest.mark.asyncio
async def test_review_pool_bounds_hosts_and_leaves_interactive_context_untouched(
    tmp_path,
):
    from mcp_open_data_hk.review_config import SOURCE_REVIEW, CONCURRENCY

    s, rows = service_with_resources(tmp_path, count=18, hosts=3)
    active = Counter()
    peak = Counter()
    context_seen = []

    async def inspect(rid, **kwargs):
        host = urlsplit(s.resources.catalogue.resource(rid)["url"]).hostname
        active[host] += 1
        active["total"] += 1
        peak[host] = max(peak[host], active[host])
        peak["total"] = max(peak["total"], active["total"])
        context_seen.append(SOURCE_REVIEW.get())
        await asyncio.sleep(0.02)
        active[host] -= 1
        active["total"] -= 1

    s.resources.schema = inspect
    task = asyncio.create_task(
        RefreshQueue(s.resources.catalogue).run(s.resources, 18, 5)
    )
    await asyncio.sleep(0)
    assert not SOURCE_REVIEW.get()
    result = await task
    assert result["processed"] == len(rows) and result["failed"] == 0
    assert peak.pop("total") == CONCURRENCY
    assert max(peak.values()) <= 2
    assert all(context_seen) and not SOURCE_REVIEW.get()
    assert s.resources.slots._value == 2  # Interactive admission remains reserved.


@pytest.mark.asyncio
async def test_concurrent_review_stops_at_persisted_daily_budget(tmp_path):
    from mcp_open_data_hk.review_config import DAILY_REVIEW_BUDGET

    s, _ = service_with_resources(tmp_path, count=12, hosts=3)
    with s.store.connect() as db:
        db.execute(
            "INSERT INTO budgets VALUES (?,?,?)",
            (
                "resource_maintenance",
                int(time.time() // 86400),
                DAILY_REVIEW_BUDGET - 2,
            ),
        )

    async def inspect(*args, **kwargs):
        await asyncio.sleep(0)

    s.resources.schema = inspect
    result = await RefreshQueue(s.resources.catalogue).run(s.resources, 12, 5)
    assert result["processed"] == 2 and result["budgetExhausted"]
    with s.store.connect() as db:
        assert (
            db.execute(
                "SELECT count FROM budgets WHERE source='resource_maintenance'"
            ).fetchone()[0]
            == DAILY_REVIEW_BUDGET
        )


@pytest.mark.asyncio
async def test_deadline_awaits_started_tasks_and_leaves_unattempted_work_due(tmp_path):
    s, _ = service_with_resources(tmp_path, count=12, hosts=3)
    active = 0

    async def inspect(*args, **kwargs):
        nonlocal active
        active += 1
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    s.resources.schema = inspect
    q = RefreshQueue(s.resources.catalogue)
    result = await q.run(s.resources, 12, 1.1)
    assert result["deadlineReached"] and result["failed"] == 0
    assert result["deferred"] == result["processed"]
    assert active == 0 and len(q.due(12, time.time())) == 12
    with s.store.connect() as db:
        assert (
            db.execute("SELECT sum(failures) FROM resource_review_policy").fetchone()[0]
            == 0
        )


def test_policy_upgrade_recovers_non_source_cooldowns_only(tmp_path):
    s, rows = service_with_resources(tmp_path)
    q = RefreshQueue(s.resources.catalogue)
    q.prepare()
    now = time.time()
    with s.store.connect() as db:
        for row, status in zip(rows, ["queryable", "restricted"]):
            db.execute(
                "INSERT INTO resource_checks(id,status,validated,checked) VALUES (?,?,?,?)",
                (row["id"], status, now - 172800, now - 100),
            )
        db.execute(
            "UPDATE resource_review_policy SET failures=1,last_attempt=?,next_due=?",
            (now - 10, now + 3600),
        )
        db.execute("UPDATE resource_review_setup SET revision='source-review-7'")
    q.prepare()
    assert [row["id"] for row in q.due(10, now)] == [rows[0]["id"]]
    with s.store.connect() as db:
        policies = list(
            db.execute(
                "SELECT id,failures,next_due FROM resource_review_policy ORDER BY id"
            )
        )
    assert policies[0]["failures"] == 0
    assert policies[1]["failures"] == 1 and policies[1]["next_due"] > now


def test_failed_previously_accepted_sources_remain_visible_as_overdue(tmp_path):
    s, rows = service_with_resources(tmp_path)
    with s.store.connect() as db:
        db.execute(
            "INSERT INTO resource_checks(id,status,validated,checked) VALUES (?,?,?,?)",
            (rows[0]["id"], "unavailable", time.time() - 172800, time.time()),
        )
    RefreshQueue(s.resources.catalogue).prepare()
    state = s.resources.catalogue.coverage()["validationFreshness"]
    assert state["reviewOverdueCount"] == 0
    assert state["overdueAcceptedCount"] == 1 and state["health"] == "degraded"


@pytest.mark.asyncio
async def test_cancelled_review_awaits_children_before_releasing_its_caller(tmp_path):
    s, _ = service_with_resources(tmp_path, count=12, hosts=3)
    active = 0
    started = asyncio.Event()

    async def inspect(*args, **kwargs):
        nonlocal active
        active += 1
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            active -= 1

    s.resources.schema = inspect
    task = asyncio.create_task(
        RefreshQueue(s.resources.catalogue).run(s.resources, 12, 10)
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert active == 0


@pytest.mark.asyncio
async def test_real_reader_reserves_interactive_slots_during_six_background_reads(
    tmp_path, monkeypatch
):
    from mcp_open_data_hk.review_config import SOURCE_REVIEW

    s, rows = service_with_resources(tmp_path, count=20, hosts=3)
    active = 0
    full = asyncio.Event()
    release = asyncio.Event()

    async def source(url, *args, **kwargs):
        nonlocal active
        if SOURCE_REVIEW.get():
            active += 1
            if active == 6:
                full.set()
            try:
                await release.wait()
            finally:
                active -= 1
        return b"id,value\n1,ok\n", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    task = asyncio.create_task(
        RefreshQueue(s.resources.catalogue).run(s.resources, 18, 5)
    )
    try:
        await asyncio.wait_for(full.wait(), 2)
        # These resources are outside the selected review batch. Public requests
        # must finish while all six background downloads are still blocked.
        results = await asyncio.wait_for(
            asyncio.gather(
                *(s.resources.schema(r["id"], require_fresh=True) for r in rows[18:])
            ),
            2,
        )
        assert all(r["recordCount"] == 1 for r in results) and active == 6
    finally:
        release.set()
        await task


@pytest.mark.asyncio
async def test_review_304_after_eviction_validates_metadata_without_inventing_records(
    tmp_path, monkeypatch
):
    import threading
    from mcp_open_data_hk.review_config import SOURCE_REVIEW

    s, rows = service_with_resources(tmp_path)
    rid = rows[0]["id"]
    requests = []
    accept_calls = []
    original = s.resources.catalogue.accept

    def accept(*args, **kwargs):
        assert threading.current_thread() is not threading.main_thread()
        accept_calls.append(True)
        return original(*args, **kwargs)

    async def source(url, headers=None, **kwargs):
        requests.append(headers or {})
        if (headers or {}).get("If-None-Match") == '"accepted"':
            return b"", {"etag": '"accepted"'}, url, 304
        return b"id,value\n1,actual\n2,source\n", {"etag": '"accepted"'}, url, 200

    monkeypatch.setattr(s.resources.catalogue, "accept", accept)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    first = await s.resources.schema(rid, require_fresh=True)
    old = s.resources.catalogue.check(rid)
    with s.store.connect() as db:
        db.execute("DELETE FROM resource_cache")
    token = SOURCE_REVIEW.set(True)
    try:
        reviewed = await s.resources.schema(rid, require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert reviewed["recordCount"] == first["recordCount"] == 2
    assert len(accept_calls) == 1
    check = s.resources.catalogue.check(rid)
    assert check["hash"] == old["hash"] and check["retrieved"] == old["retrieved"]
    assert check["validated"] >= old["validated"]
    with s.store.connect() as db:
        assert db.execute("SELECT count(*) FROM resource_cache").fetchone()[0] == 0
    actual = await s.resources.query(rid, require_fresh=True)
    assert actual["data"]["items"] == [
        {"id": "1", "value": "actual"},
        {"id": "2", "value": "source"},
    ]
    assert requests == [{}, {"If-None-Match": '"accepted"'}, {}]
    with s.store.connect() as db:
        db.execute("DELETE FROM resource_cache")
        key = db.execute(
            "SELECT key FROM resource_variants WHERE resource=?", (rid,)
        ).fetchone()[0]
    s.resources.catalogue.failure(rid, "SOURCE_UNAVAILABLE", "unavailable", key)
    token = SOURCE_REVIEW.set(True)
    try:
        recovered = await s.resources.schema(rid, require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert recovered["recordCount"] == 2 and requests[-1] == {}
    assert s.resources.catalogue.check(rid)["status"] == "queryable"


@pytest.mark.asyncio
async def test_due_review_revalidates_even_when_cached_body_is_inside_request_ttl(
    tmp_path, monkeypatch
):
    s, rows = service_with_resources(tmp_path, count=1)
    rid = rows[0]["id"]
    calls = []

    async def source(url, headers=None, **kwargs):
        calls.append(headers or {})
        if (headers or {}).get("If-None-Match") == '"actual-source"':
            return b"", {"etag": '"actual-source"'}, url, 304
        return b"id,value\n1,actual\n", {"etag": '"actual-source"'}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    await s.resources.schema(rid)
    old = time.time() - 7 * 3600  # Daily source review is 6h; file cache TTL is 24h.
    with s.store.connect() as db:
        db.execute("UPDATE resource_checks SET validated=? WHERE id=?", (old, rid))
        db.execute(
            "UPDATE resource_variants SET validated=? WHERE resource=?", (old, rid)
        )
    q = RefreshQueue(s.resources.catalogue)
    result = await q.run(s.resources, 1, 5)
    assert result["processed"] == 1 and result["failed"] == 0
    assert calls == [{}, {"If-None-Match": '"actual-source"'}]
    assert s.resources.catalogue.check(rid)["validated"] > old


def test_stale_304_cannot_validate_a_concurrently_changed_representation(tmp_path):
    s, rows = service_with_resources(tmp_path)
    rid = rows[0]["id"]
    schema = {"fields": [{"name": "id", "types": ["string"]}]}
    prior = s.resources.catalogue.accept(
        rid, "exact-key", [{"id": "1"}], schema, "old", {"etag": '"old"'}
    )
    with s.store.connect() as db:
        db.execute("UPDATE resource_variants SET hash='new' WHERE key='exact-key'")
    with pytest.raises(DomainError, match="CONCURRENT_RESOURCE_CHANGE"):
        s.resources.catalogue.revalidate(rid, "exact-key", prior, {})
    current = s.resources.catalogue.check(rid, "exact-key")
    assert current["hash"] == "new" and current["validated"] == prior["validated"]


@pytest.mark.asyncio
async def test_hko_documented_empty_warning_adopts_legacy_schema_and_keeps_other_drift_held(
    tmp_path, monkeypatch
):
    from mcp_open_data_hk.source_contracts import annotate

    s = Service(Store(str(tmp_path / "weather.sqlite3")))
    dataset = {
        "id": "hk-hko-rss-current-weather-report",
        "title": "Current weather",
        "provider": "HKO",
        "catalogue": "DATA.GOV.HK",
        "sourceUrl": "https://data.gov.hk/",
    }
    resource = {
        "id": "a" * 32,
        "datasetId": dataset["id"],
        "url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
        "format": "JSON",
        "catalogue": "DATA.GOV.HK",
        "sourceUrl": "https://data.gov.hk/",
        "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
    }
    s.resources.catalogue.publish([dataset], [resource], {})
    payload = {
        "warningMessage": ["a warning"],
        "temperature": {"data": []},
        "icon": [54],
    }

    async def source(url, *args, **kwargs):
        return json.dumps(payload).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    monkeypatch.setattr(
        "mcp_open_data_hk.resources.annotate_source_contract", lambda *args: None
    )
    old = await s.resources.schema(resource["id"], require_fresh=True)
    assert "sourceContract" not in old["schema"]
    monkeypatch.setattr("mcp_open_data_hk.resources.annotate_source_contract", annotate)
    payload["warningMessage"] = ""
    with s.store.connect() as db:
        db.execute("DELETE FROM resource_cache")
    current = await s.resources.query(resource["id"], require_fresh=True)
    assert current["data"]["items"][0]["warningMessage"] == ""
    assert current["schema"]["sourceContract"]["id"] == "hko-rhrread-warning-1"
    assert next(
        f for f in current["schema"]["fields"] if f["name"] == "warningMessage"
    )["types"] == ["string"]
    payload["warningMessage"] = ["another warning"]
    with s.store.connect() as db:
        db.execute("DELETE FROM resource_cache")
    await s.resources.schema(resource["id"], require_fresh=True)
    payload["temperature"] = "unexpected changed field"
    with s.store.connect() as db:
        db.execute("DELETE FROM resource_cache")
    with pytest.raises(DomainError, match="SCHEMA_DRIFT"):
        await s.resources.schema(resource["id"], require_fresh=True)


def test_hko_warning_contract_is_source_scoped_and_rejects_invalid_warning_values():
    from mcp_open_data_hk.source_contracts import annotate

    resource = {
        "datasetId": "hk-hko-rss-current-weather-report",
        "url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread",
    }
    schema = {"fields": [{"name": "warningMessage", "types": ["string"]}]}
    for wrong in [
        {**resource, "datasetId": "another-source"},
        {**resource, "url": "https://example.gov.hk/weather.php?dataType=rhrread"},
    ]:
        candidate = json.loads(json.dumps(schema))
        annotate(wrong, [{"warningMessage": ""}], candidate)
        assert "sourceContract" not in candidate
    for value in ["non-empty string", None, 3, ["text", 4]]:
        with pytest.raises(DomainError, match="SOURCE_SCHEMA_CHANGED"):
            annotate(
                resource, [{"warningMessage": value}], json.loads(json.dumps(schema))
            )
