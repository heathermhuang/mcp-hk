"""Real-layout contracts with invented facts; private development never enables production."""

import hashlib
import io
import json
import zipfile
from urllib.parse import parse_qs

import httpx
import pytest
from fastmcp import Client

from mcp_open_data_hk.curated.racing import prototype_store
from mcp_open_data_hk.curated.racing.policy import RacingRejected
from mcp_open_data_hk.curated.racing.prototype import PrototypeReader, create_app
from mcp_open_data_hk.curated.racing.prototype_store import (
    PilotCollector,
    PrototypeStore,
)
from mcp_open_data_hk.curated.racing.public_results import (
    COLUMNS,
    parse_results,
    result_url,
)

BASE = "https://racing.hkjc.com/en-us/local/information/localresults?racedate=2026/10/21&Racecourse=HV"


def page(
    number=1, zh=False, reverse=False, placing="1", time="1:40.39", withdrawn=False
):
    lang = "zh-hk" if zh else "en-us"
    headings = [c[int(zh)] for c in COLUMNS]
    if zh:
        headings = [h[:2] + "<br>" + h[2:] if len(h) > 2 else h for h in headings]
    values = [
        placing,
        "6",
        f'<a href="/{lang}/local/information/horse?horseid=HK_2024_TEST1">'
        + ("測試馬" if zh else "TEST HORSE")
        + "</a> (T001)",
        f'<a href="/{lang}/local/information/jockeyprofile?jockeyid=TESTJ">'
        + ("測試騎師" if zh else "TEST JOCKEY")
        + "</a>",
        f'<a href="/{lang}/local/information/trainerprofile?trainerid=TESTT">'
        + ("測試練馬師" if zh else "TEST TRAINER")
        + "</a>",
        "128",
        "1224",
        "1",
        "---",
        "4 4 4 1",
        time,
        "2.9",
    ]
    if reverse:
        headings.reverse()
        values.reverse()
    links = "".join(
        f'<a href="/{lang}/local/information/localresults?racedate=2026/10/21&amp;Racecourse=HV&amp;RaceNo={n}">Race {n}</a>'
        for n in (1, 2)
        if n != number
    )
    header = "".join("<td>" + h + "</td>" for h in headings)
    row = "".join("<td>" + v + "</td>" for v in values)
    extra = ""
    if withdrawn:
        w = values[:]
        w[0], w[1], w[6], w[7], w[9], w[10], w[11] = (
            "WX",
            "",
            "---",
            "---",
            "---",
            "---",
            "---",
        )
        w[2] = w[2].replace("HK_2024_TEST1", "HK_2024_TEST2")
        extra = "<tr>" + "".join("<td>" + v + "</td>" for v in w) + "</tr>"
    return f"""<div class="localResults"><div class="top_races">{links}</div>
    <div class="raceMeeting_select"><p><span>21/10/2026 {'跑馬地' if zh else 'Happy Valley'}</span></p></div>
    <div class="race_tab"><table><thead><tr><td>{'第 '+str(number)+' 場' if zh else 'RACE '+str(number)} (119)</td></tr></thead>
    <tbody><tr><td>Class 4 - 1650M</td><td>Going :</td><td>GOOD</td></tr><tr><td>TEST HANDICAP</td><td>Course :</td><td>TURF</td></tr></tbody></table></div>
    <table class="draggable"><thead><tr>{header}</tr></thead><tbody><tr>{row}</tr>{extra}</tbody></table>
    <table><tr><td>Commentary excluded from parsed data</td></tr></table></div>"""


def client(handler=None):
    def default(request):
        q = parse_qs(request.url.query.decode())
        return httpx.Response(
            200,
            text=page(int(q.get("RaceNo", ["1"])[0]), "/zh-hk/" in request.url.path),
            headers={"content-type": "text/html"},
        )

    return httpx.Client(transport=httpx.MockTransport(handler or default))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(prototype_store.time, "sleep", lambda _: None)
    return PrototypeStore(tmp_path / "private.sqlite3")


@pytest.mark.parametrize(
    "zh,reverse", [(False, False), (True, False), (False, True), (True, True)]
)
def test_actual_layout_semantics_and_reordered_bilingual_columns(zh, reverse):
    parsed = parse_results(
        page(zh=zh, reverse=reverse), BASE.replace("/en-us/", "/zh-hk/") if zh else BASE
    )
    row = parsed["race"]["results"][0]
    assert parsed["meeting"]["date"] == "2026-10-21"
    assert sorted(parsed["inventory"]) == [1, 2]
    assert row["participantId"] == "hkjc:horse:HK_2024_TEST1"
    assert row["horseNumber"] == "6" and row["draw"] == "1"
    assert row["timeSeconds"] == "100.39"
    assert row["weightLb"] == "128" and row["bodyWeightLb"] == "1224"
    assert row["claimLb"] is None and row["winOddsFinal"] == "2.9"
    assert "Commentary excluded" not in json.dumps(parsed)


@pytest.mark.parametrize(
    "url",
    [
        BASE.replace("racing.hkjc.com", "evil.test"),
        BASE + "&url=https://evil.test",
        BASE + "&Racecourse=ST",
        BASE.replace("2026/10/21", "bad"),
        BASE + "#fragment",
        BASE.replace("https://", "http://"),
        BASE + "&RaceNo=21",
    ],
)
def test_fixed_routes_only(url):
    with pytest.raises(RacingRejected):
        result_url(url)


def test_unknown_layout_result_and_wrong_date_fail_closed():
    for html in (
        page().replace("Act. Wt.", "Future Weight"),
        page(placing="FUTURE"),
        page().replace("21/10/2026", "20/10/2026"),
    ):
        with pytest.raises(RacingRejected):
            parse_results(html, BASE)


def test_real_withdrawal_shape_preserves_missing_number_draw_and_time():
    withdrawn = parse_results(page(withdrawn=True), BASE)["race"]["results"][1]
    assert withdrawn["status"] == "withdrawn" and withdrawn["placingRaw"] == "WX"
    assert withdrawn["horseNumber"] is None and withdrawn["draw"] is None
    assert withdrawn["timeSeconds"] is None and withdrawn["bodyWeightLb"] is None
    assert withdrawn["winOddsFinal"] is None


def test_collection_resume_versions_and_private_reader(store):
    result = PilotCollector(store, client()).collect("2026-10-21", "HV")
    assert (
        result["coverage"]["expectedRaces"] == result["coverage"]["observedRaces"] == 2
    )
    assert result["coverage"]["resultRows"] == 2
    assert result["coverage"]["declaredRunnerReconciliation"] == "not_yet_verified"
    assert (
        result["sourceLicence"] == "unverified"
        and not result["publicRedistributionEnabled"]
    )

    def no_network(request):
        raise AssertionError("resume or reads must not contact the provider")

    assert (
        PilotCollector(store, client(no_network)).collect("2026-10-21", "HV")["version"]
        == result["version"]
    )
    reader = PrototypeReader(store)
    race = reader.races()["data"]["items"][0]
    row = reader.results(race["id"], result["version"])["data"]["results"][0]
    profile = reader.profile(row["horse"]["id"], result["version"])
    assert len(profile["data"]["appearances"]) == 2
    assert profile["data"]["identity"]["nameZhHant"] == "測試馬"
    with store.connect() as db:
        assert db.execute("select count(*) from racing_attempts").fetchone()[0] == 4

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

    newer = PilotCollector(store, client(amended), refresh=True).collect(
        "2026-10-21", "HV"
    )
    assert newer["version"] != result["version"]
    assert (
        reader.results(race["id"], result["version"])["data"]["results"][0][
            "timeSeconds"
        ]
        == "100.39"
    )
    assert (
        reader.results(race["id"], newer["version"])["data"]["results"][0][
            "timeSeconds"
        ]
        == "100.40"
    )
    assert store.path.stat().st_mode & 0o777 == 0o600


def test_bilingual_conflict_never_advances_snapshot(store):
    valid = PilotCollector(store, client()).collect("2026-10-21", "HV")

    def conflict(request):
        return httpx.Response(
            200,
            text=page(
                zh="/zh-hk/" in request.url.path,
                time="1:40.40" if "/zh-hk/" in request.url.path else "1:40.39",
            ),
            headers={"content-type": "text/html"},
        )

    with pytest.raises(RacingRejected, match="BILINGUAL_FACT_MISMATCH"):
        PilotCollector(store, client(conflict), refresh=True).collect(
            "2026-10-21", "HV"
        )
    assert store.read()["version"] == valid["version"]


@pytest.mark.parametrize("status", [302, 403, 429, 503])
def test_provider_holds_survive_new_collector_and_cannot_be_layout_reconciled(
    store, status
):
    with pytest.raises(RacingRejected, match="DEVELOPMENT_HTTP_"):
        PilotCollector(
            store,
            client(
                lambda r: httpx.Response(
                    status, headers={"location": "https://evil.test"}
                )
            ),
        ).collect("2026-10-21", "HV")
    with pytest.raises(RacingRejected, match="DEVELOPMENT_SOURCE_HELD"):
        PilotCollector(store, client()).collect("2026-10-21", "HV")
    digest = hashlib.sha256(
        prototype_store.Path(prototype_store.__file__)
        .with_name("public_results.py")
        .read_bytes()
        + prototype_store.Path(prototype_store.__file__)
        .with_name("normalize.py")
        .read_bytes()
    ).hexdigest()
    with pytest.raises(RacingRejected, match="HOLD_NOT_RECONCILABLE"):
        store.reconcile_parser_fix(1, digest)


def test_interrupted_reservation_and_daily_budget_persist(store):
    store.reserve(BASE)
    with pytest.raises(RacingRejected, match="SOURCE_HELD"):
        PrototypeStore(store.path).reserve(BASE)
    with store.connect() as db:
        db.execute(
            "update racing_attempts set state='success',bytes=?", (64 * 1024 * 1024,)
        )
    with pytest.raises(RacingRejected, match="DAILY_BUDGET"):
        store.reserve(BASE)


def test_checksum_detection_and_archive_manifest(store):
    snapshot = PilotCollector(store, client()).collect("2026-10-21", "HV")
    reader = PrototypeReader(store)
    packed = reader.archive(snapshot["version"], snapshot["races"][0]["id"])
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["scope"] == "private_development"
        for name, entry in manifest["files"].items():
            raw = archive.read(name)
            assert (
                len(raw) == entry["bytes"]
                and hashlib.sha256(raw).hexdigest() == entry["sha256"]
            )
        assert "'---" in archive.read("results.csv").decode("utf-8-sig")
    with store.connect() as db:
        db.execute(
            "update racing_snapshots set payload=replace(payload,?,?)",
            ("100.39", "100.38"),
        )
    with pytest.raises(RacingRejected, match="CHECKSUM_MISMATCH"):
        store.read(snapshot["version"])


@pytest.mark.asyncio
async def test_private_rest_mcp_parity_and_local_boundary(store):
    snapshot = PilotCollector(store, client()).collect("2026-10-21", "HV")
    app = create_app(store)
    race = snapshot["races"][0]["id"]
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://127.0.0.1"
        ) as http,
        Client(app.state.mcp) as mcp,
    ):
        rest = (
            await http.get(
                "/api/v1/racing/races/" + race + "/results",
                params={"version": snapshot["version"]},
            )
        ).json()
        tool = (
            await mcp.call_tool(
                "hk_racing_results", {"raceId": race, "version": snapshot["version"]}
            )
        ).data
        assert rest == tool
        assert (await http.get("/")).status_code == 200
        assert (await http.get("/assets/prototype.js")).status_code == 200
        assert (await http.get("/assets/style.css")).status_code == 200
        assert (
            await http.get(
                "/api/v1/racing/status", headers={"Origin": "https://evil.test"}
            )
        ).status_code == 403
        assert (
            await http.get("/api/v1/racing/status", headers={"Origin": "null"})
        ).status_code == 403
        assert (
            await http.get("/api/v1/racing/status", headers={"Host": "mcp.hk"})
        ).status_code == 400
        assert (
            await http.get(
                "/api/v1/racing/exports",
                params={"version": snapshot["version"], "raceId": race},
            )
        ).headers["content-type"] == "application/zip"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app, client=("203.0.113.1", 9999)),
        base_url="http://127.0.0.1",
    ) as remote:
        assert (await remote.get("/api/v1/racing/status")).status_code == 403


def test_private_import_does_not_publish_production(tmp_path):
    from mcp_open_data_hk.racing_store import RacingStore

    public = RacingStore(tmp_path / "production.sqlite3")
    assert public.meetings() == []
    assert public.pending() is None


def test_collector_reconciles_official_chinese_dead_heat_suffix(store):
    def response(request):
        query = parse_qs(request.url.query.decode())
        zh = "/zh-hk/" in request.url.path
        return httpx.Response(
            200,
            text=page(
                int(query.get("RaceNo", ["1"])[0]),
                zh=zh,
                placing="1 平頭馬" if zh else "1 DH",
            ),
            headers={"content-type": "text/html"},
        )

    snapshot = PilotCollector(store, client(response)).collect("2026-10-21", "HV")
    for race in snapshot["races"]:
        result = race["results"][0]
        assert result["placingRaw"] == "1 DH"
        assert result["placing"] == 1 and result["deadHeat"] is True
        assert result["horse"]["nameZhHant"] == "測試馬"
