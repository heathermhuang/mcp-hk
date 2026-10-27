"""Real PostgreSQL contracts with synthetic source reports; no provider network."""

import hashlib
import os
import subprocess
import uuid

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from hkex_daily_support import DAY, menu, report
from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.read import Reader, ReadError
from mcp_open_data_hk.curated.hkex_daily import store
from mcp_open_data_hk.curated.hkex_daily.runner import collect
from mcp_open_data_hk.curated.hkex_daily.read import DailyReader


def held_inspection_fixture(c):
    from mcp_open_data_hk.curated.hkex_daily.inspection import PATH, ORIGINAL_SHA

    c.execute("INSERT INTO hkex_daily.runs(id,provenance) VALUES('original','manual')")
    c.execute(
        "INSERT INTO hkex_daily.requests(id,run_id,path,state,status,received_bytes,reserved_bytes,sha256) VALUES(142,'original',%s,'received',302,159,409600,%s)",
        (PATH, ORIGINAL_SHA),
    )
    c.execute(
        "UPDATE hkex_daily.control SET hold_code='SOURCE_ACCESS_HOLD',hold_until=NULL"
    )
    return {
        "action": "inspect_exact_legacy_response_once",
        "serial": "DA20030606000076",
        "originalLedgerId": 142,
        "retainHold": True,
        "followRedirects": False,
        "evidenceRef": "synthetic-test-only",
        "evidenceSha256": "a" * 64,
    }


DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated real PostgreSQL lane",
)


class Source:
    def __init__(self, day=DAY, denied=None, malformed=False, changed=False):
        self.day, self.denied, self.malformed, self.calls = day, denied, malformed, []
        self.changed = changed
        self.etag = '"changed-source"' if changed else '"synthetic-source"'

    def get(self, path, headers):
        self.calls.append((path, headers))
        if self.denied:
            return self.denied, b"denied", {"retry-after": "7200"}
        if path.endswith("Menu.htm"):
            return 200, menu(self.day), {"content-type": "text/html"}
        k = int(path[-5])
        body = report(k, self.day, amendment=k == 2)
        if self.malformed:
            body = body.replace(b">00005<", b">00006<")
        if self.changed:
            body = body.replace(b"Synthetic issuer", b"Changed issuer")
        if headers.get("If-None-Match") == self.etag and not self.malformed:
            return 304, b"", {}
        return 200, body, {"content-type": "text/html", "etag": self.etag}


@pytest.fixture
def model(monkeypatch):
    assert DSN, "CURATED_REQUIRE_DB requires CURATED_TEST_DSN"
    monkeypatch.setattr(store, "MIN_INTERVAL", 0)
    token = uuid.uuid4().hex[:10]
    db, restored, role = ("hd_" + token, "hd_restore_" + token, "hd_reader_" + token)
    config = conninfo_to_dict(DSN)
    owner = make_conninfo(**dict(config, dbname=db))
    restore_dsn = make_conninfo(**dict(config, dbname=restored))
    with connect(DSN, autocommit=True) as c:
        for name in (db, restored):
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        c.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    restore_names = [restored]
    try:
        store.migrate(owner)
        store.grant_reader(owner, role)
        serving = dict(config, dbname=db, user=role)
        serving.pop("password", None)
        shared = Reader(
            make_conninfo(**serving), b"synthetic-daily-summary-secret-at-least-32bytes"
        )
        yield dict(
            owner=owner,
            restore=restore_dsn,
            database=db,
            restored=restored,
            reader=DailyReader(shared),
            role=role,
            restored_databases=restore_names,
        )
    finally:
        with connect(DSN, autocommit=True) as c:
            for name in [db, *restore_names]:
                c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def intake(model, source=None):
    return collect(model["owner"], transport=source or Source(), today=DAY, lookback=1)


def qualify(model, result, tmp_path):
    container = os.environ.get("CURATED_TEST_CONTAINER")
    assert container
    archive = tmp_path / "daily.dump"
    with archive.open("wb") as out:
        subprocess.run(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                model["database"],
                "-Fc",
                "-n",
                "hkex_daily",
                "--no-owner",
                "--no-acl",
            ],
            stdout=out,
            check=True,
            timeout=30,
        )
    target = model["restored"]
    if len(model["restored_databases"]) > 1 or model.get("restored_once"):
        target = "hd_restore_" + uuid.uuid4().hex[:12]
        with connect(DSN, autocommit=True) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        model["restored_databases"].append(target)
    model["restored_once"] = True
    restored_dsn = make_conninfo(**dict(conninfo_to_dict(DSN), dbname=target))
    with archive.open("rb") as src:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                target,
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            stdin=src,
            check=True,
            timeout=30,
        )
    proof = store.qualify(
        model["owner"],
        restored_dsn,
        result["version"],
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    store.publish(model["owner"], result["version"])
    return proof


def test_all_table_restore_gate_signed_pages_and_read_only_grants(model, tmp_path):
    result = intake(model)
    assert result["state"] == "staged", result
    assert model["reader"].status()["state"] == "not_published"
    with pytest.raises(ValueError, match="RESTORE_REQUIRED"):
        store.publish(model["owner"], result["version"])
    with pytest.raises(ValueError, match="INDEPENDENT_RESTORE"):
        store.qualify(model["owner"], model["owner"], result["version"], "a" * 64)
    proof = qualify(model, result, tmp_path)
    assert set(proof["allTables"]) == set(store.TABLES)
    assert proof["allTables"]["records"]["rows"] == 4
    reader = model["reader"]
    status = reader.status()
    assert status["coverage"]["rows"] == 4
    page = reader.query("disclosures", {"limit": 1})
    next_page = reader.query(
        "disclosures",
        {"limit": 1, "cursor": page["nextCursor"], "version": page["version"]},
    )
    assert page["data"][0]["id"] != next_page["data"][0]["id"]
    r = reader.query(
        "disclosure", {"recordId": page["data"][0]["id"], "version": page["version"]}
    )
    assert r["data"] == page["data"][0] and r["data"]["filed_date"] is None
    assert len(reader.query("disclosures", {"stockCode": "5"})["data"]) == 4
    with pytest.raises(ReadError, match="does not match"):
        reader.query("disclosures", {"stockCode": "1", "cursor": page["nextCursor"]})
    with pytest.raises(ValueError, match="PUBLICATION_CONFLICT"):
        store.publish(model["owner"], result["version"])
    from psycopg.errors import InsufficientPrivilege

    with connect(reader.shared.dsn) as c:
        with pytest.raises(InsufficientPrivilege):
            c.execute("DELETE FROM hkex_daily.control")
    with pytest.raises(ValueError, match="SELECT_ONLY_ROLE"):
        store.grant_reader(model["owner"], "postgres")


def test_unchanged_conditional_reports_do_not_publish_new_version(model, tmp_path):
    first = intake(model)
    qualify(model, first, tmp_path)
    source = Source()
    second = intake(model, source)
    assert second["state"] == "unchanged", second
    assert len(source.calls) == 5 and all(h for _, h in source.calls[1:])
    assert model["reader"].status()["version"] == first["version"]
    with connect(model["owner"]) as c:
        assert c.execute("SELECT count(*) FROM hkex_daily.versions").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM hkex_daily.requests").fetchone()[0] == 10
        assert (
            c.execute(
                "SELECT count(*) FROM hkex_daily.requests WHERE status=304"
            ).fetchone()[0]
            == 4
        )


@pytest.mark.parametrize("status", [403, 429])
def test_access_and_rate_denials_hold_without_dropping_accepted_data(
    model, tmp_path, status
):
    first = intake(model)
    qualify(model, first, tmp_path)
    source = Source(denied=status)
    result = intake(model, source)
    assert result["state"] == "failed" and len(source.calls) == 1
    following = Source()
    assert intake(model, following)["code"] == "SOURCE_HOLD" and following.calls == []
    assert model["reader"].status()["version"] == first["version"]
    assert len(model["reader"].query("disclosures", {})["data"]) == 4
    with connect(model["owner"]) as c:
        hold = c.execute(
            "SELECT hold_until IS NULL FROM hkex_daily.control"
        ).fetchone()[0]
        assert hold == (status == 403)


def test_latest_schema_drift_is_not_empty_and_unknown_crash_is_not_reissued(
    model, tmp_path
):
    first = intake(model)
    qualify(model, first, tmp_path)
    result = intake(model, Source(malformed=True))
    assert result["code"] == "SUMMARY_STOCK_IDENTITY_CHANGED", result
    assert model["reader"].status()["version"] == first["version"]
    # Model a process crash after reservation, not a completed HTTP failure.
    with connect(model["owner"]) as c:
        c.execute("UPDATE hkex_daily.control SET hold_code=NULL,hold_until=NULL")
        run = uuid.uuid4().hex
        c.execute(
            "INSERT INTO hkex_daily.runs(id,provenance) VALUES(%s,'manual')", (run,)
        )
        c.execute(
            "INSERT INTO hkex_daily.requests(run_id,path,state,reserved_bytes) VALUES(%s,'/di/summary/NSMSumMenu.htm','unknown',2097152)",
            (run,),
        )
    source = Source()
    assert (
        intake(model, source)["code"] == "SOURCE_REQUEST_RECONCILIATION_REQUIRED"
        and not source.calls
    )


def test_actual_writer_lock_and_request_cap_are_enforced(model):
    with store.writer(model["owner"]):
        with pytest.raises(ValueError, match="SOURCE_WRITER_BUSY"):
            intake(model)
    source = Source()
    with connect(model["owner"]) as c:
        run = uuid.uuid4().hex
        c.execute(
            "INSERT INTO hkex_daily.runs(id,provenance) VALUES(%s,'manual')", (run,)
        )
        for i in range(100):
            c.execute(
                "INSERT INTO hkex_daily.requests(run_id,path,state,reserved_bytes,received_bytes) VALUES(%s,%s,'received',2097152,0)",
                (run, f"/prior/{i}"),
            )
    assert (
        intake(model, source)["code"] == "SOURCE_BUDGET_EXHAUSTED" and not source.calls
    )


@pytest.mark.asyncio
async def test_private_rest_mcp_summary_value_parity(model, tmp_path, monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.curated.backend import create_app as backend_app
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    result = intake(model)
    qualify(model, result, tmp_path)
    monkeypatch.setenv("MCP_HK_HKEX_DAILY_ENABLED", "true")
    service = Service(Store(tmp_path / "gateway.sqlite3"))
    service.companies.config = (
        "http://backend",
        "synthetic-only-backend-secret-32chars",
    )
    service.companies.transport = httpx.ASGITransport(
        app=backend_app(model["reader"].shared, service.companies.config[1])
    )
    app = create_app(service)
    with TestClient(app) as c:
        status = c.get("/api/v1/hkex/latest/status")
        assert status.status_code == 200, status.text
        page = c.get("/api/v1/hkex/latest/disclosures")
        assert page.status_code == 200, page.text
        key = page.json()["data"]["items"][0]["id"]
        detail = c.get(
            "/api/v1/hkex/latest/disclosures/" + key,
            params={"version": result["version"]},
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["source_search_ref"] == "100"
        assert "issuer_id" not in detail.json()["data"]
        assert c.get("/api/v1/hkex/latest/disclosures?limit=101").status_code == 400
        assert c.get("/api/v1/hkex/latest/disclosures/" + key).status_code == 400
        assert c.get("/api/v1/hkex/status").json()["state"] == "source_unqualified"
    async with Client(app.state.mcp) as c:
        names = {x.name for x in await c.list_tools()}
        assert {
            "hk_hkex_latest_status",
            "hk_hkex_latest_disclosures",
            "hk_hkex_latest_disclosure",
        } <= names
        mcp = (
            await c.call_tool(
                "hk_hkex_latest_disclosure",
                {"recordId": key, "version": result["version"]},
            )
        ).data
        assert mcp == detail.json()


def test_changed_then_reverted_summary_creates_new_revisions_and_keeps_old_cursors(
    model, tmp_path
):
    first = intake(model)
    qualify(model, first, tmp_path)
    old_page = model["reader"].query("disclosures", {"limit": 1})
    second = intake(model, Source(changed=True))
    assert second["state"] == "staged" and second["version"] != first["version"], second
    qualify(model, second, tmp_path)
    pinned = model["reader"].query(
        "disclosures", {"limit": 1, "cursor": old_page["nextCursor"]}
    )
    assert pinned["version"] == first["version"]
    reverted = intake(model, Source())
    assert reverted["state"] == "staged" and reverted["version"] not in {
        first["version"],
        second["version"],
    }, reverted
    qualify(model, reverted, tmp_path)
    with connect(model["owner"]) as c:
        assert (
            c.execute("SELECT accepted_revision FROM hkex_daily.control").fetchone()[0]
            == 3
        )
    assert model["reader"].status()["version"] == reverted["version"]
    source = Source()
    assert intake(model, source)["state"] == "unchanged"
    assert all(headers for _, headers in source.calls[1:])


def test_exact_approved_inspection_is_charged_once_and_cannot_release_hold(model):
    import httpx
    from mcp_open_data_hk.curated.hkex_daily.inspection import inspect, reserve, PATH

    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "/login?session=NEVER_RETAIN"},
            content=b"synthetic redirect",
        )

    with store.writer(model["owner"]) as c:
        approval = held_inspection_fixture(c)
        with pytest.raises(ValueError, match="SOURCE_HOLD"):
            store.reserve(c, "original", PATH)
        receipt = inspect(
            c, uuid.uuid4().hex, approval, transport=httpx.MockTransport(response)
        )
        assert (
            receipt["holdRetained"] and receipt["redirect"]["sanitizedLocation"] is None
        )
        assert "NEVER_RETAIN" not in str(receipt) and len(calls) == 1
        assert c.execute(
            "SELECT hold_code,hold_until FROM hkex_daily.control"
        ).fetchone() == {"hold_code": "SOURCE_ACCESS_HOLD", "hold_until": None}
        assert (
            c.execute(
                "SELECT count(*) AS n FROM hkex_daily.requests WHERE state='received'"
            ).fetchone()["n"]
            == 2
        )
        with pytest.raises(ValueError, match="ALREADY_RESERVED"):
            reserve(c, uuid.uuid4().hex, approval)
        with pytest.raises(ValueError, match="SOURCE_HOLD"):
            store.reserve(c, "original", PATH)


def test_hold_inspection_requires_exact_approval_and_preserves_unknown_budget(model):
    import httpx
    from mcp_open_data_hk.curated.hkex_daily.inspection import inspect, reserve

    def interrupted(request):
        raise httpx.ReadTimeout("synthetic interrupted response")

    with store.writer(model["owner"]) as c:
        approval = held_inspection_fixture(c)
        for field, value in [
            ("serial", "other"),
            ("followRedirects", True),
            ("retainHold", False),
        ]:
            with pytest.raises(ValueError, match="EXPLICIT_EXACT"):
                reserve(c, uuid.uuid4().hex, dict(approval, **{field: value}))
        with pytest.raises(httpx.ReadTimeout):
            inspect(
                c,
                uuid.uuid4().hex,
                approval,
                transport=httpx.MockTransport(interrupted),
            )
        assert (
            c.execute(
                "SELECT reserved_bytes FROM hkex_daily.requests WHERE state='unknown'"
            ).fetchone()["reserved_bytes"]
            == 409600
        )
        with pytest.raises(ValueError, match="ALREADY_RESERVED"):
            reserve(c, uuid.uuid4().hex, approval)
        assert (
            c.execute("SELECT hold_code FROM hkex_daily.control").fetchone()[
                "hold_code"
            ]
            == "SOURCE_ACCESS_HOLD"
        )


def test_hold_inspection_cannot_exceed_shared_daily_allowance(model):
    from mcp_open_data_hk.curated.hkex_daily.inspection import reserve

    with store.writer(model["owner"]) as c:
        approval = held_inspection_fixture(c)
        for index in range(99):
            c.execute(
                "INSERT INTO hkex_daily.requests(run_id,path,state,reserved_bytes,received_bytes) VALUES('original',%s,'received',409600,1)",
                ("synthetic-" + str(index),),
            )
        with pytest.raises(ValueError, match="BUDGET_EXHAUSTED"):
            reserve(c, uuid.uuid4().hex, approval)
        assert (
            c.execute("SELECT count(*) AS n FROM hkex_daily.runs").fetchone()["n"] == 1
        )
