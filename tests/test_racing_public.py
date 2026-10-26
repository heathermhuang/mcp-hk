"""Production racing publishes real structured facts only after restored checkpoint proof."""

import copy
import hashlib
import json
import zipfile
import io

import httpx
import pytest
from fastmcp import Client

from test_racing_prototype import client
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.sources import DISTRICTS
from mcp_open_data_hk.operations import checkpoint, restore
from mcp_open_data_hk.racing_store import RacingStore
from mcp_open_data_hk.curated.racing.prototype_store import (
    PrototypeStore,
    PilotCollector,
)
from mcp_open_data_hk.curated.racing.policy import RacingRejected


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.racing.prototype_store.time.sleep", lambda _: None
    )
    private = PrototypeStore(tmp_path / "private.sqlite3")
    snapshot = PilotCollector(private, client()).collect("2026-10-21", "HV")
    with private.connect() as db:
        pages = [dict(r) for r in db.execute("SELECT * FROM racing_pages")]
        attempts = [dict(r) for r in db.execute("SELECT * FROM racing_attempts")]
    return {"snapshot": snapshot, "pages": pages, "attempts": attempts}


@pytest.fixture
def service(tmp_path):
    store = Store(str(tmp_path / "source" / "app.sqlite3"))
    store.publish(
        "restaurants", [{"id": "fixture", "latitude": 22.3, "longitude": 114.1}], None
    )
    store.publish(
        "population",
        [{"id": d["id"] + ":2024", "districtId": d["id"]} for d in DISTRICTS],
        None,
    )
    return Service(store)


def accept(service, pilot, tmp_path):
    candidate = service.racing.store.import_bundle(pilot)
    archive, digest = checkpoint(service.store.path)
    target = tmp_path / "isolated" / "restored.sqlite3"
    restore(archive.read_bytes(), digest, str(target))
    proof = service.racing.store.accept_restored(
        RacingStore(target), candidate["version"], digest
    )
    return candidate, proof


def test_staging_hidden_then_all_source_facts_restore_and_publish(
    service, pilot, tmp_path
):
    before = service.store.active("restaurants")
    candidate = service.racing.store.import_bundle(pilot)
    assert service.racing.store.meetings() == []
    with pytest.raises(RacingRejected):
        service.racing.store.read(candidate["version"])
    assert service.racing.store.pending() == candidate["version"]
    _, proof = accept(service, pilot, tmp_path)
    read = service.racing.store.read(candidate["version"])
    assert read["scope"] == "public_factual_results" and "sourceLicence" not in read
    assert proof["raceCount"] == 2 and proof["resultRows"] == 2
    assert service.racing.store.pending() is None
    assert service.store.active("restaurants") == before
    with service.racing.store.connect() as db:
        assert db.execute("SELECT count(*) FROM racing_attempts").fetchone()[0] == 4
    service.racing.store.import_bundle(pilot)
    with service.racing.store.connect() as db:
        assert db.execute("SELECT count(*) FROM racing_attempts").fetchone()[0] == 4


def test_modified_snapshot_and_full_control_state_fail_restore(
    service, pilot, tmp_path
):
    candidate = service.racing.store.import_bundle(pilot)
    archive, digest = checkpoint(service.store.path)
    target = tmp_path / "isolated" / "restored.sqlite3"
    restore(archive.read_bytes(), digest, str(target))
    restored = RacingStore(target)
    with restored.connect() as db:
        db.execute("UPDATE racing_attempts SET bytes=bytes+1 WHERE id=1")
    with pytest.raises(RacingRejected, match="RACING_RESTORE_MISMATCH"):
        service.racing.store.accept_restored(restored, candidate["version"], digest)
    assert service.racing.store.meetings() == []


def test_superseded_candidate_cannot_rollback_current(service, pilot, tmp_path):
    old, _ = accept(service, pilot, tmp_path)
    newer = copy.deepcopy(pilot["snapshot"])
    newer.pop("version")
    newer["observedAt"] = "2026-10-25T12:00:00+00:00"
    candidate = service.racing.store.publish(newer)
    assert candidate["version"] != old["version"]
    assert service.racing.store.read()["version"] == old["version"]
    assert service.racing.store.pending() == candidate["version"]


@pytest.mark.parametrize("change", ["row", "capture", "inventory", "unknown", "tie"])
def test_bad_import_never_changes_accepted_pointer(service, pilot, tmp_path, change):
    accepted, _ = accept(service, pilot, tmp_path)
    bad = copy.deepcopy(pilot)
    s = bad["snapshot"]
    if change == "row":
        s["races"][0]["results"][0]["timeSeconds"] = "0.00"
    elif change == "capture":
        s["provenance"][0]["url"] = "https://evil.test"
    elif change == "inventory":
        s["coverage"]["expectedRaces"] = 99
    elif change == "unknown":
        s["races"][0]["results"][0]["placingRaw"] = "NEW_CODE"
    else:
        s["races"][0]["results"][0]["deadHeat"] = True
    raw = dict(s)
    raw.pop("version")
    from mcp_open_data_hk.curated.racing.policy import checksum

    s["version"] = "private-results-v1-" + checksum(raw)
    with pytest.raises((RacingRejected, KeyError)):
        service.racing.store.import_bundle(bad)
    assert service.racing.store.read()["version"] == accepted["version"]


@pytest.mark.asyncio
async def test_actual_public_rest_mcp_pinned_values_export(service, pilot, tmp_path):
    accepted, _ = accept(service, pilot, tmp_path)
    app = create_app(service)
    version = accepted["version"]
    rid = accepted["races"][0]["id"]
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as http,
        Client(app.state.mcp) as mcp,
    ):
        rest = (
            await http.get(
                "/api/v1/racing/races/" + rid + "/results", params={"version": version}
            )
        ).json()
        remote = (
            await mcp.call_tool(
                "hk_racing_results", {"raceId": rid, "version": version}
            )
        ).data
        assert rest == remote and rest["data"]["results"][0]["timeSeconds"] == "100.39"
        assert (
            await http.get("/api/v1/racing/races", params={"version": version})
        ).json()["meta"]["version"] == version
        archive = await http.get(
            "/api/v1/racing/exports", params={"raceId": rid, "version": version}
        )
        assert archive.status_code == 200
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
            manifest = json.loads(zipped.read("manifest.json"))
            for name, entry in manifest["files"].items():
                raw = zipped.read(name)
                assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert (await http.get("/api/v1/racing/status")).json()["data"][
            "state"
        ] == "available"


def test_queue_resumes_at_one_request_and_does_not_publish_before_backup(
    service, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.racing.prototype_store.time.sleep", lambda _: None
    )
    store = service.racing.store
    store.enqueue([{"date": "2026-10-21", "venue": "HV"}])
    for _ in range(4):
        store.advance(1, client())
    assert store.pending() is not None and store.meetings() == []
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM racing_attempts").fetchone()[0] == 4
        assert db.execute("SELECT state FROM racing_queue").fetchone()[0] == "staged"


def test_observed_withdrawn_at_start_code_has_no_finish_time():
    from mcp_open_data_hk.curated.racing.normalize import placing, result_row

    assert placing("WV-A")["status"] == "withdrawn"
    with pytest.raises(RacingRejected, match="NON_FINISHER_TIME"):
        result_row(
            {
                "horseId": "TEST",
                "horseNumber": "7",
                "draw": None,
                "placing": "WV-A",
                "time": "1:09.00",
                "weightLb": "123",
                "claimLb": None,
                "marginRaw": "---",
            },
            "race",
        )


def test_fixture_inventory_excludes_no_programme_and_unchanged_discovery_stops(service):
    from datetime import datetime, timezone
    from mcp_open_data_hk.racing_calendar import parse_fixture, FIXTURE

    now = datetime.now(timezone.utc)
    text = f'<p>{now.month}/{now.year}</p><table><tr><td class="calendar">1<img alt="ST">1200(9)</td><td class="calendar">2<img alt="HV">Meeting cancelled</td></tr></table>'
    url = FIXTURE + f"?calyear={now.year}&calmonth={now.month:02d}"
    parsed = parse_fixture(text, url)
    assert (
        parsed["meetings"][0]["plannedRaces"] == 9
        and parsed["meetings"][1]["plannedRaces"] == 0
    )
    calls = []
    transport = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                calls.append(str(r.url))
                or httpx.Response(200, text=text, headers={"content-type": "text/html"})
            )
        )
    )
    result = service.racing.store.calendar(now.year, now.month, transport)
    assert result["eligibleMeetings"] == int(now.day > 1)
    before = service.racing.store.fingerprint()
    assert service.racing.store.discover_due()["state"] == "unchanged"
    assert service.racing.store.fingerprint() == before and len(calls) == 1


def test_fixture_wrong_period_is_unavailable_not_complete_empty():
    from mcp_open_data_hk.racing_calendar import parse_fixture, FIXTURE

    text = (
        '<p>10/2026</p><table><td class="calendar">1<img alt="ST">1200(9)</td></table>'
    )
    parsed = parse_fixture(text, FIXTURE + "?calyear=2025&calmonth=09")
    assert parsed["state"] == "period_unavailable" and parsed["meetings"] == []


def test_refresh_checkpoint_never_mixes_old_chinese_with_new_english(
    service, pilot, tmp_path, monkeypatch
):
    from test_racing_prototype import page
    from urllib.parse import parse_qs

    monkeypatch.setattr(
        "mcp_open_data_hk.curated.racing.prototype_store.time.sleep", lambda _: None
    )
    old, _ = accept(service, pilot, tmp_path)
    store = service.racing.store
    store.enqueue([{"date": "2026-10-21", "venue": "HV"}], True)
    for _ in range(4):

        def amended(request):
            q = parse_qs(request.url.query.decode())
            return httpx.Response(
                200,
                text=page(
                    int(q.get("RaceNo", ["1"])[0]),
                    "/zh-hk/" in request.url.path,
                    time="1:40.40",
                ),
                headers={"content-type": "text/html"},
            )

        store.advance(1, httpx.Client(transport=httpx.MockTransport(amended)))
    pending = store.pending()
    assert pending and pending != old["version"]
    assert store.raw(pending)["races"][0]["results"][0]["timeSeconds"] == "100.40"
    assert store.read()["version"] == old["version"]


def test_production_admission_precedes_http_and_cold_replica_cannot_reset_it(
    service, monkeypatch
):
    monkeypatch.setenv("MCP_HK_EDGE_MODE", "true")
    store = service.racing.store
    calls = []

    def admission(body):
        calls.append(body)
        return (
            {"allowed": True, "id": body["id"]}
            if body["action"] == "reserve"
            else {"settled": True}
        )

    monkeypatch.setattr(store, "admission", admission)
    attempt = store.reserve(
        "https://racing.hkjc.com/en-us/local/information/localresults?racedate=2026/10/21&Racecourse=HV"
    )
    assert calls[0]["action"] == "reserve"
    store.settled(attempt, "success", 123)
    assert calls[1]["action"] == "settle" and calls[1]["id"] == calls[0]["id"]

    def held(body):
        return {"allowed": False, "code": "RACING_SOURCE_HELD"}

    monkeypatch.setattr(store, "admission", held)
    with pytest.raises(RacingRejected, match="RACING_SOURCE_HELD"):
        store.reserve(
            "https://racing.hkjc.com/en-us/local/information/localresults?racedate=2026/10/21&Racecourse=HV"
        )


@pytest.mark.asyncio
async def test_operator_import_can_exceed_public_body_limit_but_stays_authenticated(
    service, pilot, monkeypatch
):
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", "racing-test-only-token")
    app = create_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://testserver"
    ) as http:
        body = {"action": "import", "bundle": pilot, "padding": "x" * 70000}
        response = await http.post(
            "/__ops/racing",
            json=body,
            headers={"Authorization": "Bearer racing-test-only-token"},
        )
        assert response.status_code == 200 and response.headers[
            "x-racing-candidate"
        ].startswith("racing-results-v1-")
        assert (
            await http.post("/__ops/racing", json={"action": "advance"})
        ).status_code == 404
        assert (await http.post("/mcp", content=b"x" * 70000)).status_code == 413


def test_missing_source_placing_is_not_invented_as_a_withdrawal_or_zero():
    from mcp_open_data_hk.curated.racing.normalize import result_row, placing

    value = result_row(
        {
            "horseId": "TEST",
            "horseNumber": "4",
            "draw": None,
            "placing": "",
            "time": None,
            "weightLb": "124",
            "claimLb": None,
            "marginRaw": "---",
        },
        "race",
    )
    assert (
        value["placingRaw"] == ""
        and value["placing"] is None
        and value["status"] == "not_reported"
        and value["timeSeconds"] is None
    )
    for code in ("WR", "WV-A", "WX-A", "WXNR"):
        assert placing(code)["status"] == "withdrawn"
    assert placing("TNP")["status"] == "took_no_part"
    with pytest.raises(RacingRejected, match="UNKNOWN_RESULT_CODE"):
        placing("FUTURE_CODE")


def test_mcp_ingestion_metadata_uses_authenticated_request_context(
    service, monkeypatch
):
    monkeypatch.setenv("MCP_HK_EDGE_MODE", "true")
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", "racing-edge-fixture-only")
    report = {"durable": True, "attempts": 46, "unresolved": []}
    monkeypatch.setattr(
        "fastmcp.server.dependencies.get_http_headers",
        lambda: {
            "x-mcp-edge-token": "racing-edge-fixture-only",
            "x-mcp-racing-budget": json.dumps(report),
        },
    )
    assert service.racing.reader.status()["data"]["durableIngestion"] == report
    monkeypatch.setattr(
        "fastmcp.server.dependencies.get_http_headers",
        lambda: {
            "x-mcp-edge-token": "forged",
            "x-mcp-racing-budget": json.dumps(report),
        },
    )
    assert service.racing.reader.status()["data"]["durableIngestion"] is None
