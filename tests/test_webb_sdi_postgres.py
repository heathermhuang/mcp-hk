"""Synthetic source contracts on real PostgreSQL; full release receipts are separate."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from test_webb_sdi import fixture_source
from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.read import Reader, ReadError
from mcp_open_data_hk.curated.webb_sdi_read import WebbSdiReader
from mcp_open_data_hk.curated import webb_sdi_store as store
from mcp_open_data_hk.curated.webb_sdi_source import canonical, extract

DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated PostgreSQL lane runs these contracts",
)


@pytest.fixture
def model(tmp_path, monkeypatch):
    assert DSN, "CURATED_REQUIRE_DB requires CURATED_TEST_DSN"
    source = tmp_path / "source"
    member, sha, census = fixture_source(source)
    notice = Path(store.__file__).parents[1] / "webb-site-NOTICE.txt"
    (source / "webb-site-NOTICE.txt").write_bytes(notice.read_bytes())
    projection = tmp_path / "projection"
    extract(source, projection, data_path=member, expected_sha=sha, census=census)
    manifest = json.loads((projection / "manifest.json").read_text())
    # Deliberately synthetic: two issuers share a stock code, two filings have
    # the same event day, an old legacy key has no serial and dates stay unknown.
    first = json.loads((projection / "sdi.ndjson").read_text())
    first["serNoSuper"] = "TEST_002"
    second = dict(
        first,
        ID="2",
        stockCode="5",
        serNo="TEST_002",
        serNoAmend="TEST_001",
        serNoSuper=None,
    )
    third = dict(
        first,
        ID="3",
        issueID="11",
        stockName="Other synthetic issuer",
        relDate=None,
        serNo=None,
        filing="123",
        serNoSuper="MISSING",
    )
    issue = json.loads((projection / "issue.ndjson").read_text())
    for table, records in {
        "sdi": [first, second, third],
        "issue": [issue, dict(issue, ID1="11", issuer="101")],
    }.items():
        data = b"".join(canonical(r) + b"\n" for r in records)
        (projection / (table + ".ndjson")).write_bytes(data)
        manifest["tables"][table] = {
            "rows": len(records),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    (projection / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(store, "DATA_SHA", sha)
    token = uuid.uuid4().hex[:10]
    db, restored, role = (p + token for p in ("wsdi_", "wsdi_restore_", "wsdi_reader_"))
    config = conninfo_to_dict(DSN)
    owner = make_conninfo(**dict(config, dbname=db))
    restore_dsn = make_conninfo(**dict(config, dbname=restored))
    with connect(DSN, autocommit=True) as admin:
        for name in (db, restored):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    try:
        store.migrate(owner)
        loaded = store.stage(owner, projection)
        store.grant_reader(owner, role)
        serving = dict(config, dbname=db, user=role)
        serving.pop("password", None)
        shared = Reader(
            make_conninfo(**serving), b"webb-sdi-fixture-secret-at-least-32-bytes"
        )
        yield dict(
            owner=owner,
            restore=restore_dsn,
            database=db,
            restored=restored,
            version=manifest["version"],
            reader=WebbSdiReader(shared),
            projection=projection,
            manifest=loaded,
        )
    finally:
        with connect(DSN, autocommit=True) as admin:
            for name in (db, restored):
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def qualify(model, tmp_path):
    container = os.environ.get("CURATED_TEST_CONTAINER")
    assert container, "Physical restore requires CURATED_TEST_CONTAINER"
    archive = tmp_path / "webb-sdi.dump"
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
                "webb_sdi",
                "--no-owner",
                "--no-acl",
            ],
            stdout=out,
            check=True,
            timeout=30,
        )
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
                model["restored"],
                "--no-owner",
                "--no-acl",
                "--exit-on-error",
            ],
            stdin=src,
            check=True,
            timeout=30,
        )
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    proof = store.qualify_restore(
        model["owner"], model["restore"], model["version"], sha
    )
    store.publish(model["owner"], model["version"], None)
    return proof


def test_full_restore_gate_cas_and_read_only_source_identity(model, tmp_path):
    assert model["reader"].status()["state"] == "not_published"
    with pytest.raises(ValueError, match="RESTORE_QUALIFIED"):
        store.publish(model["owner"], model["version"], None)
    with pytest.raises(ValueError, match="INDEPENDENT_RESTORE"):
        store.qualify_restore(
            model["owner"], model["owner"], model["version"], "a" * 64
        )
    proof = qualify(model, tmp_path)
    assert len(proof["allTables"]) == 7 and proof["allTables"]["filings"]["rows"] == 3
    with pytest.raises(ValueError, match="PUBLICATION_CONFLICT"):
        store.publish(model["owner"], model["version"], None)
    reader = model["reader"]
    assert reader.status()["coverage"]["issuerCount"] == 2
    found = reader.query("issuers", {"stockCode": "00005", "limit": 1})
    assert found["data"][0]["issuer_id"] == "webb:person:100"
    other = reader.query(
        "issuers", {"stockCode": "00005", "limit": 1, "cursor": found["nextCursor"]}
    )
    assert other["data"][0]["issuer_id"] == "webb:person:101"
    with pytest.raises(ReadError, match="does not match"):
        reader.query("issuers", {"q": "Other", "cursor": found["nextCursor"]})
    assert (
        reader.query("issuers", {"q": "Ｓｙｎｔｈｅｔｉｃ"})["data"][0][
            "archive_filings"
        ]
        == 2
    )
    # A SELECT-only service cannot delete accepted records.
    from psycopg.errors import InsufficientPrivilege

    with connect(reader.shared.dsn) as c:
        with pytest.raises(InsufficientPrivilege):
            c.execute("DELETE FROM webb_sdi.accepted")


def test_cursor_ties_precision_unknown_dates_and_revision_gaps(model, tmp_path):
    qualify(model, tmp_path)
    reader = model["reader"]
    params = {"issuerId": "webb:person:100", "limit": 1}
    first = reader.query("disclosures", params)
    second = reader.query("disclosures", dict(params, cursor=first["nextCursor"]))
    assert [first["data"][0]["id"], second["data"][0]["id"]] == [
        "webb:sdi:2",
        "webb:sdi:1",
    ]
    detail = reader.query("disclosure", {"filingId": "1", "version": first["version"]})[
        "data"
    ]
    assert detail["before"]["long_shares"] == "9007199254740993.00000001"
    assert (
        detail["awareness_date"]
        is detail["filed_date"]
        is detail["published_date"]
        is None
    )
    assert (
        detail["capacities"][0]["position"] == detail["events"][0]["position"] == "long"
    )
    assert detail["revision_links"][0]["filing_id"] == "webb:sdi:2"
    missing = reader.query("disclosure", {"filingId": "3"})["data"]
    assert missing["serial"] is None and missing["legacy_filing_key"] == "123"
    assert (
        missing["event_date"] is None and not missing["revision_links"][0]["resolved"]
    )
    assert "ccc" not in json.dumps(detail)
    assert reader.query(
        "disclosures", dict(params, start="2000-01-01", end="2000-01-02")
    )["data"]
    assert not reader.query(
        "disclosures", dict(params, start="1999-12-31", end="2000-01-01")
    )["data"]
    with pytest.raises(ReadError, match="1–31"):
        reader.query("disclosures", dict(params, start="2000-01-01", end="2001-01-01"))


def test_modified_projection_and_different_restored_content_fail_closed(
    model, tmp_path
):
    path = model["projection"] / "sdi.ndjson"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="PROJECTION_CHECKSUM"):
        store.stage(model["owner"], model["projection"])
    store.migrate(model["restore"])
    with pytest.raises(ValueError, match="RESTORE_CONTENT_MISMATCH"):
        store.qualify_restore(
            model["owner"], model["restore"], model["version"], "a" * 64
        )
    assert model["reader"].status()["state"] == "not_published"


@pytest.mark.asyncio
async def test_rest_mcp_parity_uses_private_postgres_without_fresh_hkex(
    model, tmp_path, monkeypatch
):
    import httpx
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.curated.backend import create_app as backend_app
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    qualify(model, tmp_path)
    monkeypatch.setenv("MCP_HK_WEBB_SDI_ENABLED", "true")
    service = Service(Store(tmp_path / "gateway.sqlite3"))
    service.companies.config = (
        "http://backend",
        "test-only-backend-credential-32-chars",
    )
    service.companies.transport = httpx.ASGITransport(
        app=backend_app(model["reader"].shared, service.companies.config[1])
    )
    app = create_app(service)
    params = {"version": model["version"]}
    with TestClient(app) as public:
        rest = public.get("/api/v1/hkex/archive/disclosures/1", params=params)
        assert rest.status_code == 200, rest.text
        assert rest.json()["data"]["id"] == "webb:sdi:1"
        assert (
            public.get("/api/v1/hkex/archive/issuers?stockCode=00005").status_code
            == 200
        )
        assert public.get("/api/v1/hkex/archive/disclosures/1").status_code == 400
        assert (
            public.get(
                "/api/v1/hkex/archive/disclosures/BAD!", params=params
            ).status_code
            == 400
        )
        assert public.get("/api/v1/hkex/status").json()["state"] == "source_unqualified"
    async with Client(app.state.mcp) as client:
        assert {
            "hk_hkex_archive_issuers",
            "hk_hkex_archive_disclosures",
            "hk_hkex_archive_disclosure",
        } <= {t.name for t in await client.list_tools()}
        mcp = (
            await client.call_tool(
                "hk_hkex_archive_disclosure", {"filingId": "1", **params}
            )
        ).data
        assert mcp == rest.json()
