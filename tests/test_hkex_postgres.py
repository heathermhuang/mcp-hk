"""Mandatory real PostgreSQL source isolation, journals, publication and recovery."""

import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from hkex_support import SyntheticAdapter, day, filing, policy, window
from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.hkex.collect import Collector
from mcp_open_data_hk.curated.hkex.contracts import digest
from mcp_open_data_hk.curated.hkex.read import HkexReader
from mcp_open_data_hk.curated.hkex.recovery import backup, build_export, restore
from mcp_open_data_hk.curated.hkex.store import (
    Store,
    accept_restore,
    activate_policy,
    grant_reader,
    migrate,
)
from mcp_open_data_hk.curated.read import ReadError, Reader

DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated PostgreSQL lane runs these contracts",
)


@pytest.fixture
def model(monkeypatch, tmp_path):
    # Synthetic disk/headroom measurement only. The production 20 GiB guard is
    # exercised negatively below; this is not evidence of host capacity.
    monkeypatch.setenv("HKEX_STORAGE_ROOT", str(tmp_path))
    from collections import namedtuple

    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda path: usage(100 * 1024**3, 40 * 1024**3, 60 * 1024**3),
    )
    assert DSN, "CURATED_REQUIRE_DB requires CURATED_TEST_DSN"
    config = conninfo_to_dict(DSN)
    token = uuid.uuid4().hex[:10]
    database, restored, role, writer = [
        prefix + token
        for prefix in ("hkex_", "hkex_restore_", "hkex_read_", "hkex_write_")
    ]
    admin_dsn = make_conninfo(**dict(config, dbname=database))
    restore_dsn = make_conninfo(**dict(config, dbname=restored))
    with connect(DSN, autocommit=True) as c:
        for db in (database, restored):
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
        for r in (role, writer):
            c.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(r)))
    try:
        with connect(admin_dsn) as c:
            c.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            c.execute(
                sql.SQL("CREATE SCHEMA hkex AUTHORIZATION {}").format(
                    sql.Identifier(writer)
                )
            )
            c.execute(
                "CREATE SCHEMA curated; CREATE TABLE curated.sentinel(id integer)"
            )
        writer_dsn = make_conninfo(**dict(config, dbname=database, user=writer))
        migrate(writer_dsn)
        migrate(writer_dsn)
        grant_reader(writer_dsn, role)
        p = policy()
        activate_policy(writer_dsn, p.model_dump(mode="json"), digest(p))
        shared = Reader(
            make_conninfo(**dict(config, dbname=database, user=role)),
            b"hkex-test-only-secret-at-least-32bytes",
        )
        store = Store(writer_dsn, digest(p))

        # No sleep in deterministic fixtures. Simulate a provider cadence boundary
        # after each local adapter response; the engine still enforces it in SQL.
        def paced(kind, key):
            with connect(writer_dsn) as c:
                c.execute(
                    "UPDATE hkex.control SET last_read_at=now()-interval '2 seconds'"
                )

        yield dict(
            store=store,
            policy=p,
            reader=HkexReader(shared),
            owner=writer_dsn,
            admin=admin_dsn,
            restored=restore_dsn,
            role=role,
            paced=paced,
        )
    finally:
        with connect(DSN, autocommit=True) as c:
            for db in (database, restored):
                c.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db))
                )
            for r in (role, writer):
                c.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(r)))


def collect(model, rows=None, **kwargs):
    rows = rows if rows is not None else [filing()]
    adapter = SyntheticAdapter(rows, after=model["paced"], **kwargs)
    result = Collector(model["store"], adapter).run(
        window(), datetime.now(timezone.utc)
    )
    return result, adapter


def qualify(model, version, tmp_path):
    assert shutil.which("pg_dump") and shutil.which(
        "pg_restore"
    ), "Install PostgreSQL tools for real restore contracts"
    archive = tmp_path / "hkex.dump"
    info = backup(model["owner"], archive)
    restore(model["restored"], archive, info["sha256"])
    proof = accept_restore(model["owner"], model["restored"], version, info["sha256"])
    assert len(proof["tables"]) == 15
    model["store"].publish(version, None)
    return info


def test_source_grants_lossless_fields_and_true_restore(model, tmp_path):
    with connect(model["owner"]) as c:
        with pytest.raises(Exception):
            c.execute("INSERT INTO curated.sentinel VALUES(1)")
    rows = [
        filing(
            "A", state="superseded", superseded_by="B", filed_date=day("2026-10-01")
        ),
        filing("B", state="amendment", replaces="A"),
        filing("W", state="withdrawn", withdrawn_date=day("2026-10-15")),
    ]
    result, adapter = collect(model, rows)
    assert result["state"] == "validated", result
    assert result["coverage"]["closureOutsideWindow"] == ["A"]
    with connect(model["owner"], row_factory=dict_row) as c:
        value = c.execute(
            "SELECT shares,shares_raw FROM hkex.interests LIMIT 1"
        ).fetchone()
        assert value["shares"] == Decimal(value["shares_raw"])
        assert c.execute(
            "SELECT count(*) AS n FROM hkex.captures WHERE raw_bytes IS NOT NULL"
        ).fetchone()["n"] == len(adapter.calls)
    with pytest.raises(ValueError, match="RESTORE_PROOF"):
        model["store"].publish(result["version"], None)
    with pytest.raises(ValueError, match="INDEPENDENT"):
        accept_restore(model["owner"], model["owner"], result["version"], "a" * 64)
    qualify(model, result["version"], tmp_path)
    reader = model["reader"]
    found = reader.query("issuers", {"stockCode": "00001"})
    assert found["data"][0]["issuer_id"] == "hkex:issuer:TEST_ISSUER"
    payload = reader.query(
        "disclosure", {"filingId": "A", "version": result["version"]}
    )
    assert not payload["data"]["currently_effective_notice"]
    assert payload["data"]["published_date"]["value"] is None
    payload = reader.query(
        "disclosure", {"filingId": "W", "version": result["version"]}
    )
    assert not payload["data"]["currently_effective_notice"]
    with pytest.raises(ValueError, match="PUBLICATION_CONFLICT"):
        model["store"].publish(result["version"], None)
    with connect(reader.shared.dsn) as c:
        with pytest.raises(Exception):
            c.execute("UPDATE hkex.accepted SET version='wrong'")


def test_signed_pagination_modes_retention_and_export(model, tmp_path):
    result, _ = collect(model, [filing("A"), filing("B")])
    assert result["state"] == "validated", result
    qualify(model, result["version"], tmp_path)
    params = dict(
        issuerId="TEST_ISSUER",
        start="2026-10-12",
        end="2026-10-19",
        basis="filed",
        limit=1,
    )
    first = model["reader"].query("disclosures", params)
    second = model["reader"].query(
        "disclosures", dict(params, cursor=first["nextCursor"])
    )
    assert first["data"][0]["serial"] != second["data"][0]["serial"]
    with pytest.raises(ReadError, match="does not match"):
        model["reader"].query(
            "disclosures", dict(params, basis="event", cursor=first["nextCursor"])
        )
    with pytest.raises(ReadError, match="outside accepted"):
        model["reader"].query("disclosures", dict(params, basis="event"))
    info = build_export(model["reader"], result["version"], tmp_path / "export.zip")
    assert info["bytes"] > 100
    import zipfile
    import json
    import hashlib

    with zipfile.ZipFile(tmp_path / "export.zip") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["rows"] == 2
        for name, record in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == record["sha256"]
    revoked = model["policy"].model_copy(update={"revoked": True})
    activate_policy(model["owner"], revoked.model_dump(mode="json"), digest(revoked))
    assert model["reader"].status()["state"] == "source_unqualified"
    with pytest.raises(ReadError, match="not qualified"):
        model["reader"].query("disclosures", params)
    with pytest.raises(ValueError, match="EXPORT_UNQUALIFIED"):
        build_export(model["reader"], result["version"], tmp_path / "denied.zip")


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("duplicate", "INVENTORY_SERIAL_MISMATCH"),
        ("drift", "PAGE_DRIFT"),
        ("login", "SOURCE_SCHEMA_CHANGED"),
        ("denied", "SOURCE_403"),
        ("missing_date", "INDEPENDENT_DETAIL_HASH_MISMATCH"),
    ],
)
def test_incomplete_or_failed_inventory_never_publishes(model, failure, expected):
    def mutate(kind, key, doc):
        if failure == "duplicate" and kind == "listing":
            doc["serials"] *= 2
        elif failure == "drift" and kind == "listing":
            doc["snapshot"] = "changed"
        elif failure == "login" and kind == "listing":
            return 200, b"<html>login</html>", None
        elif failure == "denied" and kind == "listing":
            return 403, b"denied", None
        elif failure == "missing_date" and kind == "detail":
            doc["filed_date"] = day()
        return doc

    result, _ = collect(model, mutate=mutate)
    assert result["state"] == "failed" and result["code"] == expected, result
    with connect(model["owner"]) as c:
        assert c.execute("SELECT count(*) FROM hkex.accepted").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM hkex.requests").fetchone()[0] >= 2
        if failure == "denied":
            assert c.execute(
                "SELECT hold_until IS NULL AND hold_code='SOURCE_403_MANUAL_REVIEW' FROM hkex.control"
            ).fetchone()[0]


def test_budget_resume_unknown_reservation_and_expiry_mid_run(model):
    p = model["policy"].model_copy(update={"reads_run": 2})
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    store = Store(model["owner"], digest(p))
    scheduled = datetime.now(timezone.utc)
    adapter = SyntheticAdapter([filing()], after=model["paced"])
    result = Collector(store, adapter).run(window(), scheduled)
    assert (
        result["state"] == "partial" and result["code"] == "SOURCE_BUDGET_EXHAUSTED"
    ), result
    before = len(adapter.calls)
    assert Collector(store, adapter).run(window(), scheduled)["state"] == "partial"
    assert len(adapter.calls) == before
    # A separate slot cannot enter while another source session holds the lock.
    with store.session():
        with pytest.raises(ValueError, match="BUSY"):
            with store.session():
                pass
    # New policy breaks the previous run's pinned identity before any new read.
    revoked = p.model_copy(update={"revoked": True})
    activate_policy(model["owner"], revoked.model_dump(mode="json"), digest(revoked))
    with pytest.raises(ValueError, match="UNQUALIFIED"):
        Collector(store, adapter).run(window(), scheduled + timedelta(seconds=1))


def test_filing_inventory_basis_gate_zero_reads(model):
    p = model["policy"].model_copy(update={"inventory_basis": "event"})
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    adapter = SyntheticAdapter([filing()])
    with pytest.raises(ValueError, match="INVENTORY_UNQUALIFIED"):
        Collector(Store(model["owner"], digest(p)), adapter).run(
            window(), datetime.now(timezone.utc)
        )
    assert adapter.calls == []


def test_next_occurrence_resumes_budgeted_pilot_without_refetch(model):
    p = model["policy"].model_copy(update={"reads_run": 2})
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    store = Store(model["owner"], digest(p))
    adapter = SyntheticAdapter([filing()], after=model["paced"])
    start = datetime.now(timezone.utc)
    first = Collector(store, adapter).run(window(), start)
    assert first["state"] == "partial"
    second = Collector(store, adapter).run(window(), start + timedelta(minutes=20))
    assert second["state"] == "validated", second
    assert adapter.calls == [
        ("inventory", digest(window())),
        ("listing", "1"),
        ("detail", "TEST_001"),
    ]


def test_complete_empty_window_has_issuer_and_unknown_dates(model, tmp_path):
    result, _ = collect(model, [])
    assert result["state"] == "validated", result
    qualify(model, result["version"], tmp_path)
    assert len(model["reader"].query("issuers", {"stockCode": "00001"})["data"]) == 1
    params = dict(
        issuerId="TEST_ISSUER", start="2026-10-12", end="2026-10-19", basis="filed"
    )
    assert model["reader"].query("disclosures", params)["data"] == []


def test_midrun_revocation_and_unknown_request_are_charged(model):
    def revoke(kind, key):
        if kind == "listing":
            p = model["policy"].model_copy(update={"revoked": True})
            activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
        model["paced"](kind, key)

    adapter = SyntheticAdapter([filing()], after=revoke)
    result = Collector(model["store"], adapter).run(
        window(), datetime.now(timezone.utc)
    )
    assert (
        result["state"] == "failed" and result["code"] == "HKEX_SOURCE_UNQUALIFIED"
    ), result
    with connect(model["owner"]) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM hkex.requests WHERE state='unknown'"
            ).fetchone()[0]
            == 1
        )
        assert c.execute("SELECT count(*) FROM hkex.accepted").fetchone()[0] == 0
    # A fresh occurrence cannot turn the prior unknown read into a blind retry.
    p = model["policy"]
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    again, adapter = collect(model)
    assert again["code"] == "REQUEST_RECONCILIATION_REQUIRED" and adapter.calls == []


def test_growth_and_backup_gates_stop_before_source_read(model, monkeypatch, tmp_path):
    from collections import namedtuple

    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(100, 99, 1))
    result, adapter = collect(model)
    assert result["code"] == "HKEX_GROWTH_RESERVE_REQUIRED" and adapter.calls == []
    with pytest.raises(ValueError, match="GROWTH_RESERVE"):
        backup(model["owner"], tmp_path / "denied.dump")
    assert not (tmp_path / "denied.dump").exists()


@pytest.mark.asyncio
async def test_real_private_rest_mcp_and_browser_contract_parity(
    model, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from fastmcp import Client
    import httpx
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.curated.backend import create_app as backend_app
    from mcp_open_data_hk.hkex import Hkex
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store as GatewayStore

    result, _ = collect(model)
    qualify(model, result["version"], tmp_path)
    service = Service(GatewayStore(tmp_path / "gateway.sqlite3"))
    service.companies.config = (
        "http://backend",
        "test-only-backend-credential-32-chars",
    )
    service.companies.transport = httpx.ASGITransport(
        app=backend_app(model["reader"].shared, service.companies.config[1])
    )
    service.hkex = Hkex(service.companies, model["policy"])
    app = create_app(service)
    params = {"version": result["version"]}
    with TestClient(app) as public:
        rest = public.get("/api/v1/hkex/disclosures/TEST_001", params=params)
        browser = public.get("/api/v1/hkex/browser/disclosures/TEST_001", params=params)
        assert rest.status_code == browser.status_code == 200, rest.text
        assert rest.json() == browser.json()
        assert (
            public.get(
                "/api/v1/hkex/disclosures/hkex:di:TEST_001", params=params
            ).json()
            == rest.json()
        )
        assert "raw_bytes" not in rest.text and "source_location" not in rest.text
        assert rest.json()["data"]["capture"]["observed_at"]
        assert (
            public.get("/api/v1/hkex/disclosures/BAD!", params=params).status_code
            == 400
        )
    async with Client(app.state.mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        assert {"hk_hkex_issuers", "hk_hkex_disclosures", "hk_hkex_disclosure"} <= tools
        mcp = (
            await client.call_tool(
                "hk_hkex_disclosure",
                {"filingId": "TEST_001", "version": result["version"]},
            )
        ).data
        assert mcp == rest.json()


def test_unchanged_approved_inventory_stops_before_pages_details_or_backup(
    model, tmp_path
):
    result, _ = collect(model)
    qualify(model, result["version"], tmp_path)
    adapter = SyntheticAdapter([filing()], after=model["paced"])
    result = Collector(model["store"], adapter).run(
        window(), datetime.now(timezone.utc)
    )
    assert result["state"] == "unchanged", result
    assert adapter.calls == [("inventory", digest(window()))]


def test_status_does_not_leak_filing_inventory_or_unqualified_identity(model, tmp_path):
    result, _ = collect(model)
    qualify(model, result["version"], tmp_path)
    modes = dict(model["policy"].modes, rest="denied", mcp="unknown")
    p = model["policy"].model_copy(update={"modes": modes})
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    status = model["reader"].status()
    assert "issuer_id" not in status["coverage"]["window"]
    assert "expectedSerials" not in status["coverage"]
    assert "issuer" not in status["coverage"]


def test_capture_retention_expiry_hides_identity_and_blocks_new_export(model, tmp_path):
    result, _ = collect(model)
    qualify(model, result["version"], tmp_path)
    with connect(model["owner"]) as c:
        c.execute(
            "UPDATE hkex.versions SET manifest=jsonb_set(manifest,'{retainedUntil}',to_jsonb(%s::text)) WHERE version=%s",
            (
                (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                result["version"],
            ),
        )
    status = model["reader"].status(mode="browser")
    assert status["state"] == "version_expired"
    assert "issuer_id" not in status["coverage"]["window"]
    with pytest.raises(ReadError, match="retention expired"):
        model["reader"].query(
            "disclosure", {"filingId": "TEST_001", "version": result["version"]}
        )
    with pytest.raises(ValueError, match="EXPORT_UNQUALIFIED"):
        build_export(model["reader"], result["version"], tmp_path / "expired.zip")
    assert not (tmp_path / "expired.zip").exists()


@pytest.mark.parametrize(
    "status,retry,manual",
    [(429, 9 * 86400, False), (403, 0, True), (429, "unqualified", True)],
)
def test_provider_hold_never_shortens_delay_or_automatically_retries_denial(
    model, status, retry, manual
):
    def deny(kind, key, doc):
        return status, b"synthetic provider hold", retry

    result, _ = collect(model, mutate=deny)
    assert result["code"] == "SOURCE_" + str(status)
    with connect(model["owner"], row_factory=dict_row) as c:
        row = c.execute("SELECT hold_until,hold_code FROM hkex.control").fetchone()
        if manual:
            assert row["hold_until"] is None and row["hold_code"] in {
                "SOURCE_403_MANUAL_REVIEW",
                "SOURCE_RETRY_AFTER_UNQUALIFIED",
            }
        else:
            assert row["hold_until"] > datetime.now(timezone.utc) + timedelta(
                days=8, hours=23
            )
    again, adapter = collect(model)
    assert again["code"] == "SOURCE_HOLD" and adapter.calls == []
