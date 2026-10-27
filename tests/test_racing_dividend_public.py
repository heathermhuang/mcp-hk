"""Invented dividends use the real checkpoint-qualified public serving path."""

import csv
import hashlib
import io
import json
import zipfile
from urllib.parse import parse_qs

import httpx
import pytest
from fastmcp import Client

from test_racing_prototype import page
from test_racing_public import service as base_service, accept
from test_racing_dividends import fixture
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.curated.racing.prototype_store import (
    PrototypeStore,
    PilotCollector,
)

service = base_service


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.racing.prototype_store.time.sleep", lambda _: None
    )
    private = PrototypeStore(tmp_path / "private.sqlite3")

    def source(request):
        q = parse_qs(request.url.query.decode())
        zh = "/zh-hk/" in request.url.path
        table = fixture()
        if zh:
            table = (
                table.replace("Pool", "彩池")
                .replace("Winning Combination", "勝出組合")
                .replace("Dividend", "派彩")
                .replace("WIN", "獨贏")
                .replace("PLACE", "位置")
            )
        return httpx.Response(
            200,
            text=page(int(q.get("RaceNo", ["1"])[0]), zh) + table,
            headers={"content-type": "text/html"},
        )

    snapshot = PilotCollector(
        private, httpx.Client(transport=httpx.MockTransport(source))
    ).collect("2026-10-21", "HV")
    with private.connect() as db:
        return {
            "snapshot": snapshot,
            "pages": [dict(r) for r in db.execute("SELECT * FROM racing_pages")],
            "attempts": [dict(r) for r in db.execute("SELECT * FROM racing_attempts")],
        }


@pytest.mark.asyncio
async def test_dividends_restore_then_match_rest_mcp_and_actual_zip(
    service, pilot, tmp_path
):
    candidate, proof = accept(service, pilot, tmp_path)
    version = candidate["version"]
    race = service.racing.reader.races(version)["data"]["items"][0]
    race_id = race["id"]
    assert proof["resultRows"] == 2
    assert (
        service.racing.reader.status()["data"]["dividendCoverage"]["observedRaces"] == 2
    )
    app = create_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as http:
        response = await http.get(
            "/api/v1/racing/races/" + race_id + "/results", params={"version": version}
        )
        assert response.status_code == 200
        rest = response.json()
        async with Client(app.state.mcp) as mcp:
            tool = await mcp.call_tool(
                "hk_racing_results", {"raceId": race_id, "version": version}
            )
            assert tool.data == rest
        rows = rest["data"]["dividends"]["quotes"]
        assert len(rows) == 3 and rows[0]["stakeAmount"] is None
        packed = await http.get(
            "/api/v1/racing/exports", params={"version": version, "raceId": race_id}
        )
        assert packed.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(packed.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["dividendRows"] == 3 and manifest["rowCount"] == 1
    assert (
        "schema.json" in archive.namelist()
        and json.loads(archive.read("results.json")) == rest
    )
    decoded = list(
        csv.DictReader(io.StringIO(archive.read("dividends.csv").decode("utf-8-sig")))
    )
    assert (
        decoded[0]["winningCombinationRaw"] == "03"
        and decoded[2]["amount"] == "1020.50"
    )
    for name, member in manifest["files"].items():
        body = archive.read(name)
        assert (
            len(body) == member["bytes"]
            and hashlib.sha256(body).hexdigest() == member["sha256"]
        )


@pytest.mark.asyncio
async def test_tampered_dividend_facts_are_not_served(service, pilot, tmp_path):
    candidate, _ = accept(service, pilot, tmp_path)
    version = candidate["version"]
    with service.racing.store.connect() as db:
        payload = json.loads(
            db.execute(
                "SELECT payload FROM racing_snapshots WHERE version=?", (version,)
            ).fetchone()[0]
        )
        race_id = payload["races"][0]["id"]
        payload["races"][0]["dividends"]["quotes"][0]["amount"] = "999.00"
        db.execute(
            "UPDATE racing_snapshots SET payload=? WHERE version=?",
            (json.dumps(payload), version),
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(service)),
        base_url="http://testserver",
    ) as http:
        response = await http.get(
            "/api/v1/racing/races/" + race_id + "/results", params={"version": version}
        )
        assert response.status_code == 503
        assert (
            response.json()["error"]["code"] == "DEVELOPMENT_SNAPSHOT_CHECKSUM_MISMATCH"
        )


def test_unqualified_translation_does_not_turn_into_empty_or_unavailable_results(
    service, pilot, tmp_path
):
    snapshot = pilot["snapshot"]
    snapshot["races"][0]["dividends"] = {
        "state": "unqualified",
        "quotes": None,
        "code": "DIVIDEND_BILINGUAL_MISMATCH",
    }
    from mcp_open_data_hk.curated.racing.policy import checksum

    snapshot.pop("version")
    snapshot["version"] = "private-results-v1-" + checksum(snapshot)
    candidate, _ = accept(service, pilot, tmp_path)
    data = service.racing.reader.results(
        snapshot["races"][0]["id"], candidate["version"]
    )["data"]
    assert len(data["results"]) == 1 and data["dividends"]["quotes"] is None


def test_unreconciled_private_candidates_cannot_enter_public_snapshots(pilot):
    from mcp_open_data_hk.racing_store import validate_snapshot
    from mcp_open_data_hk.curated.racing.policy import RacingRejected

    snapshot = pilot["snapshot"]
    snapshot["races"][0]["dividendCandidate"] = {"state": "observed"}
    with pytest.raises(RacingRejected, match="UNRECONCILED_CANDIDATE"):
        validate_snapshot(snapshot)
