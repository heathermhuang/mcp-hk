"""Real PostgreSQL contract tests, mandatory in the dedicated CI lane."""

import json
import os
import uuid

import pytest

from mcp_open_data_hk.curated.build import connect, stage
from mcp_open_data_hk.curated.qualify import (
    accept_restore,
    grant_reader,
    inspect,
    publish,
)
from mcp_open_data_hk.curated.read import ReadError, Reader
from mcp_open_data_hk.curated.schema import schema_name

DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated PostgreSQL lane runs these contracts",
)


class FixtureSource:
    manifest = {"archiveSha256": "a" * 64, "view": "archive", "observedAt": None}

    def check_disk(self):
        pass

    def rows(self, table, columns, where="1"):
        records = {
            "issue": [{"issuer": 2}],
            "organisations": [
                {
                    "PersonID": 1,
                    "Domicile": 1,
                    "orgType": 19,
                    "Name1": "ＦＯＯ Limited",
                    "cName": "香港甲公司",
                    "incID": "0000123",
                },
                {
                    "PersonID": 2,
                    "Domicile": 2,
                    "orgType": 7,
                    "Name1": "Foo Holdings",
                    "cName": "香港乙公司",
                },
            ],
            "people": [{"PersonID": 3, "Name1": "CHAN", "Name2": "Tai Man"}],
            "directorships": [
                {
                    "ID1": 11,
                    "Company": 2,
                    "Director": 3,
                    "positionID": 1,
                    "ApptDate": "2020-01-01",
                    "ApptAcc": 1,
                    "ResDate": None,
                }
            ],
            "licrec": [{"ID": 21, "orgID": 1, "staffID": 3, "role": 1, "actType": 1}],
            "olicrec": [{"ID": 22, "orgID": 1, "ri": 0, "actType": 1}],
            "namechanges": [
                {
                    "ID1": 31,
                    "personID": 1,
                    "oldName": "Foo Old",
                    "dateChanged": "2020-02-01",
                    "dateAcc": 2,
                }
            ],
            "positions": [{"positionID": 1, "posLong": "Director"}],
            "activity": [{"ID": 1, "actName": "Dealing"}],
            "domiciles": [
                {"ID": 1, "FullName": "Hong Kong"},
                {"ID": 2, "FullName": "Cayman Islands"},
            ],
            "orgtypes": [
                {"orgType": 19, "typeName": "Private limited"},
                {"orgType": 7, "typeName": "Unknown"},
            ],
            "dateaccuracy": [],
            "dismodes": [],
        }[table]
        if where.startswith("PersonID IN ("):
            ids = set(map(int, where[len("PersonID IN (") : -1].split(",")))
            records = [r for r in records if r["PersonID"] in ids]
        for row in records:
            yield {c: row.get(c) for c in columns}


@pytest.fixture
def model():
    assert DSN, "CURATED_REQUIRE_DB requires CURATED_TEST_DSN"
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    token = uuid.uuid4().hex[:10]
    version, role, database = "test-" + token, "reader_" + token, "model_" + token
    config = conninfo_to_dict(DSN)
    owner = make_conninfo(**dict(config, dbname=database))
    with connect(DSN, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        with connect(owner) as conn:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        manifest = stage(owner, FixtureSource(), version)
        grant_reader(owner, role)
        serving = dict(config, dbname=database, user=role)
        serving.pop("password", None)
        reader = Reader(make_conninfo(**serving), b"fixture-secret-32-bytes-at-least!!")
        yield version, manifest, reader, role, owner
    finally:
        # Never publish into or clean up the caller's database. Each test owns
        # an entire private database, including its global publication pointer.
        with connect(DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            admin.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role))
            )


def local_accept(version, owner):
    # Integration fixtures test publication state separately from physical restore.
    # Production CLI accept-restore compares an independently restored database.
    from mcp_open_data_hk.curated.qualify import fingerprint

    with connect(owner) as conn:
        manifest = conn.execute(
            "SELECT manifest FROM curated.dataset_versions WHERE version=%s", (version,)
        ).fetchone()[0]
        proof = {"independentlyRestored": True, "manifestSha256": fingerprint(manifest)}
        conn.execute(
            "UPDATE curated.dataset_versions SET state='validated',restore_proof=%s::jsonb WHERE version=%s",
            (json.dumps(proof), version),
        )
    publish(owner, version)


def test_normalized_model_constraints_publication_and_signed_pages(model):
    version, manifest, reader, role, owner = model
    assert manifest["counts"]["entities"] == 3
    evidence = inspect(owner, version)
    assert evidence["validatedConstraints"]
    assert evidence["temporal"]["officer_appointments"]["uncertain_bounds"] == 1
    with pytest.raises(ValueError, match="must pass"):
        publish(owner, version)
    with pytest.raises(ValueError, match="independent"):
        accept_restore(owner, owner, version, "a" * 64)
    local_accept(version, owner)
    found = reader.search(name="ＦＯＯ", limit=1)
    assert found["version"] == version and found["nextCursor"]
    second = reader.search(name="foo", limit=1, cursor=found["nextCursor"])
    assert found["data"][0]["display_name"] != second["data"][0]["display_name"]
    chinese = reader.search(name="香港")
    assert len(chinese["data"]) == 2
    assert (
        reader.search(namespace="webb:incorporation:1", value="0000123")["data"][0][
            "entity_id"
        ]
        == 1
    )
    assert reader.search(namespace="webb:incorporation:1", value="123")["data"] == []
    assert reader.get(3)["data"]["name2"] == "Tai Man"
    assert reader.related(2, "officers")["data"][0]["start_precision"] == "year"
    assert reader.related(1, "names")["data"]
    with pytest.raises(ReadError, match="as-of"):
        reader.related(2, "officers", as_of="2020-01-01")
    with pytest.raises(ReadError, match="absent"):
        reader.related(999, "officers")
    with pytest.raises(ReadError, match="does not match"):
        reader.search(name="other", cursor=found["nextCursor"])
    with connect(reader.dsn) as conn:
        from psycopg.errors import InsufficientPrivilege, ReadOnlySqlTransaction

        with pytest.raises((InsufficientPrivilege, ReadOnlySqlTransaction)):
            conn.execute("DELETE FROM curated.dataset_versions")
    with pytest.raises(ReadError, match="dedicated"):
        Reader(owner, b"x" * 32).get(1)


def test_failed_stage_cannot_replace_published_release(model):
    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    bad = version + "-bad"

    class Broken(FixtureSource):
        def rows(self, table, columns, where="1"):
            if table == "people":
                return iter([])
            return super().rows(table, columns, where)

    with pytest.raises(ValueError, match="Unresolved"):
        stage(owner, Broken(), bad)
    with pytest.raises(ValueError):
        publish(owner, bad)
    assert reader.search(name="foo")["version"] == version
    from psycopg import sql

    with connect(owner) as conn:
        conn.execute("DELETE FROM curated.dataset_versions WHERE version=%s", (bad,))
        conn.execute(
            sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name(bad)))
        )


def test_private_http_matches_library_and_preserves_errors(model):
    from fastapi.testclient import TestClient
    from mcp_open_data_hk.curated.backend import create_app

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    client = TestClient(create_app(reader, "private-test-token-32-characters!!"))
    auth = {"Authorization": "Bearer private-test-token-32-characters!!"}
    assert client.get("/v1/companies?name=foo").status_code == 401
    response = client.get("/v1/companies?name=foo", headers=auth)
    assert response.status_code == 200
    assert response.json() == reader.search(name="foo")
    assert client.get("/health", headers=auth).json()["view"] == "archive"
    assert client.get("/v1/entities/999", headers=auth).status_code == 404
    assert (
        client.get("/v1/entities/2/officers?asOf=2020-01-01", headers=auth).status_code
        == 422
    )
    assert client.get("/v1/companies?name=x", headers=auth).status_code == 400
    assert (
        client.get("/v1/companies?name=foo&limit=101", headers=auth).status_code == 422
    )
    assert (
        client.get("/v1/companies?namespace=sql&value=DELETE", headers=auth).status_code
        == 400
    )


def test_actual_dump_restore_gate(tmp_path):
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from mcp_open_data_hk.curated.backup import backup, restore

    container = os.environ.get("CURATED_TEST_CONTAINER")
    assert (
        container
    ), "PostgreSQL qualification requires the owned test container for physical restore"
    token = uuid.uuid4().hex[:10]
    original, restored = "original_" + token, "restored_" + token
    version = "backup-" + token
    config = conninfo_to_dict(DSN)
    with connect(DSN, autocommit=True) as admin:
        for database in [original, restored]:
            admin.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
            )
    try:
        source_dsn = make_conninfo(**dict(config, dbname=original))
        restore_dsn = make_conninfo(**dict(config, dbname=restored))
        stage(source_dsn, FixtureSource(), version)
        from psycopg.rows import dict_row
        from mcp_open_data_hk.curated.official import DDL, weekly
        from mcp_open_data_hk.curated.official_ingest import save_capture, promote
        from pathlib import Path

        with connect(source_dsn, autocommit=True, row_factory=dict_row) as source:
            source.execute(DDL)
            body = (
                Path(__file__).parent / "fixtures/official/weekly-local.csv"
            ).read_bytes()
            capture, _ = save_capture(
                source,
                "restore-fixture",
                "https://www.cr.gov.hk/test.csv",
                body,
                {},
                parser=lambda b: weekly(b, "local", "20261012"),
            )
            official_version = promote(
                source, {"restore-fixture": capture}, {"restored": True}
            )
        proof = backup(container, original, version, tmp_path / "model.dump")
        with pytest.raises(ValueError, match="checksum"):
            restore(container, restored, tmp_path / "model.dump", "0" * 64)
        restore(container, restored, tmp_path / "model.dump", proof["sha256"])
        with connect(restore_dsn, row_factory=dict_row) as restored_conn:
            assert (
                restored_conn.execute(
                    "SELECT version FROM curated.official_pointer"
                ).fetchone()["version"]
                == official_version
            )
            assert (
                restored_conn.execute(
                    "SELECT body FROM curated.official_captures WHERE capture_id=%s",
                    (capture,),
                ).fetchone()["body"]
                == body
            )
            assert (
                restored_conn.execute(
                    "SELECT count(*) AS n FROM curated.official_records"
                ).fetchone()["n"]
                == 3
            )
        accepted = accept_restore(source_dsn, restore_dsn, version, proof["sha256"])
        assert accepted["independentlyRestored"]
        publish(source_dsn, version)
        assert (
            inspect(source_dsn, version)["counts"]
            == inspect(restore_dsn, version)["counts"]
        )
    finally:
        with connect(DSN, autocommit=True) as admin:
            for database in [original, restored]:
                admin.execute(
                    sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
                )


def test_real_statement_and_lock_timeouts(model):
    import time
    from psycopg import sql

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    started = time.monotonic()
    with pytest.raises(ReadError) as error:
        with reader.request() as (conn, _):
            conn.execute("SELECT pg_sleep(3)")
    assert error.value.code == "QUERY_TIMEOUT"
    assert 1.8 <= time.monotonic() - started < 3
    with connect(owner) as blocker:
        blocker.execute(
            sql.SQL("LOCK TABLE {}.entities IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(schema_name(version))
            )
        )
        started = time.monotonic()
        with pytest.raises(ReadError) as error:
            reader.get(1)
        assert error.value.code == "QUERY_TIMEOUT"
        assert time.monotonic() - started < 1


def test_cursor_pins_old_release_through_publication_and_rollback(model):
    from psycopg import sql

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    first = reader.search(name="foo", limit=1)
    new = version + "-next"
    try:
        stage(owner, FixtureSource(), new)
        grant_reader(owner, role)
        local_accept(new, owner)
        assert reader.search(name="foo")["version"] == new
        assert (
            reader.search(name="foo", limit=1, cursor=first["nextCursor"])["version"]
            == version
        )
        publish(owner, version)
        assert reader.search(name="foo")["version"] == version
    finally:
        with connect(owner) as conn:
            conn.execute(
                "DELETE FROM curated.dataset_versions WHERE version=%s", (new,)
            )
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(
                    sql.Identifier(schema_name(new))
                )
            )


def test_fixture_has_its_own_database(model):
    from psycopg.conninfo import conninfo_to_dict

    reader = model[2]
    assert conninfo_to_dict(reader.dsn)["dbname"] != conninfo_to_dict(DSN)["dbname"]


@pytest.mark.parametrize(
    "privilege",
    [
        "replication",
        "pg_read_server_files",
        "pg_execute_server_program",
        "pg_read_all_data",
        "noinherit",
    ],
)
def test_elevated_serving_credentials_are_rejected_at_grant_and_runtime(
    model, privilege
):
    from psycopg import sql

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    with connect(owner) as admin:
        if privilege == "replication":
            admin.execute(
                sql.SQL("ALTER ROLE {} REPLICATION").format(sql.Identifier(role))
            )
        else:
            group = "pg_read_server_files" if privilege == "noinherit" else privilege
            if privilege == "noinherit":
                admin.execute(
                    sql.SQL("ALTER ROLE {} NOINHERIT").format(sql.Identifier(role))
                )
            admin.execute(
                sql.SQL("GRANT {} TO {}").format(
                    sql.Identifier(group), sql.Identifier(role)
                )
            )
    with pytest.raises(ValueError, match="unprivileged"):
        grant_reader(owner, role)
    with pytest.raises(ReadError) as error:
        reader.get(1)
    assert error.value.code == "UNSAFE_READER"


@pytest.mark.asyncio
async def test_gateway_rest_mcp_and_discovery_share_real_backend(
    model, tmp_path, monkeypatch
):
    import httpx
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.curated.backend import create_app as private_app
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    token = "gateway-test-credential-of-32-characters"
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", token)
    monkeypatch.setattr("mcp_open_data_hk.companies.ARCHIVE_SHA", "a" * 64)
    service = Service(Store(str(tmp_path / "gateway.sqlite3")))
    service.companies.transport = httpx.ASGITransport(app=private_app(reader, token))
    service.resources.catalogue.publish(
        [
            {
                "id": "sample",
                "title": "Sample",
                "catalogue": "DATA.GOV.HK",
                "provider": "Example",
                "providerType": "government",
            }
        ],
        [],
        {},
    )
    app = create_app(service)
    cases = [
        (
            "/api/v1/companies",
            {"q": "foo", "limit": 1},
            "hk_company_search",
            {"q": "foo", "limit": 1},
        ),
        (
            "/api/v1/companies/1",
            {"version": version},
            "hk_company_get",
            {"entityId": 1, "version": version},
        ),
        (
            "/api/v1/companies/1/names",
            {"version": version},
            "hk_company_name_history",
            {"entityId": 1, "version": version},
        ),
        (
            "/api/v1/companies/2/officers",
            {"version": version},
            "hk_company_officers",
            {"entityId": 2, "version": version},
        ),
        (
            "/api/v1/companies/1/licences",
            {"version": version},
            "hk_company_licences",
            {"entityId": 1, "version": version},
        ),
        (
            "/api/v1/companies/1/licence_relationships",
            {"version": version},
            "hk_company_licence_relationships",
            {"entityId": 1, "version": version},
        ),
    ]
    with TestClient(app) as http:
        responses = [http.get(path, params=params) for path, params, _, _ in cases]
        assert all(response.status_code == 200 for response in responses), [
            r.text for r in responses
        ]
        assert http.get("/api/v1/packs").json()["items"][-1]["id"] == "enigma"
        found = http.get(
            "/api/v1/catalogue/datasets", params={"q": "enigma", "access": "connected"}
        ).json()
        assert found["items"][0]["id"] == "mcp:enigma"
        assert http.get("/api/v1/companies/3").status_code == 404
        assert http.get("/api/v1/companies/3/names").status_code == 404
        assert (
            http.get(
                "/api/v1/companies", params={"q": "foo", "requireFresh": True}
            ).status_code
            == 422
        )
        assert (
            http.get(
                "/api/v1/companies/2/officers", params={"asOf": "2020-01-01"}
            ).status_code
            == 422
        )
        assert http.get("/api/v1/companies", params={"q": "x"}).status_code == 400
        assert http.get("/healthz").status_code == 200
        assert http.get("/api/v1/companies/notice").status_code == 200
    async with Client(app.state.mcp) as mcp:
        tools = {t.name: t for t in await mcp.list_tools()}
        for response, (_, _, tool, args) in zip(responses, cases):
            actual = (await mcp.call_tool(tool, args)).data
            expected = response.json()
            assert actual["data"] == expected["data"]
            assert actual["meta"]["version"] == expected["meta"]["version"] == version
            assert actual["warnings"] == expected["warnings"]
            assert actual["provenance"][0]["archiveSha256"] == "a" * 64
            assert tools[tool].annotations.readOnlyHint
        first = responses[0].json()
        second = (
            await mcp.call_tool(
                "hk_company_search",
                {"q": "foo", "limit": 1, "cursor": first["meta"]["nextCursor"]},
            )
        ).data
        assert second["data"] != first["data"]
        assert second["meta"]["version"] == version
    party = responses[3].json()["data"]["items"][0]["party"]
    assert party["name1"] == "CHAN" and party["name2"] == "Tai Man"


def test_explicit_history_version_survives_new_publication(model):

    version, manifest, reader, role, owner = model
    local_accept(version, owner)
    next_version = version + "-new"
    stage(owner, FixtureSource(), next_version)
    grant_reader(owner, role)
    local_accept(next_version, owner)
    assert reader.related(1, "names", version=version)["version"] == version
    assert reader.get(1, version=version)["version"] == version
    assert reader.related(1, "names")["version"] == next_version


def test_public_export_is_complete_typed_and_refuses_unqualified_or_overwritten_builds(
    model, tmp_path
):
    import tarfile

    from mcp_open_data_hk.curated.export import build, verify

    version, _, reader, _, owner = model
    with pytest.raises(ValueError, match="published"):
        build(reader.dsn, version, tmp_path / "unpublished", reserve_bytes=0)
    assert (tmp_path / "unpublished" / "failed-receipt.json").exists()
    local_accept(version, owner)
    temporal = inspect(owner, version)["temporal"]
    with connect(owner) as conn:
        conn.execute(
            "UPDATE curated.dataset_versions SET restore_proof=restore_proof||%s::jsonb WHERE version=%s",
            (json.dumps({"temporal": temporal}), version),
        )
    target = tmp_path / "approved"
    publication = build(reader.dsn, version, target, reserve_bytes=0)
    verified = verify(target)
    assert verified["verified"] and verified["typedNdjsonVerified"]
    assert verified["rows"]["entities"] == 3
    assert publication["scope"] == "complete_approved_subset"
    with tarfile.open(target / "companies.tar.gz") as archive:
        entities = [json.loads(line) for line in archive.extractfile("entities.ndjson")]
        assert (
            next(r for r in entities if r["entity_id"] == 1)["chinese_name"]
            == "香港甲公司"
        )
        identifiers = [
            json.loads(line)
            for line in archive.extractfile("entity_identifiers.ndjson")
        ]
        assert any(r["value"] == "0000123" for r in identifiers)
        assert any(r["kind"] == "person" for r in entities)
        assert "birth_date" not in entities[0]
        assert b"Webb" in archive.extractfile("NOTICE.txt").read()
    with pytest.raises(FileExistsError):
        build(reader.dsn, version, target, reserve_bytes=0)
    with (target / "companies.tar.gz").open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        verify(target)


def test_official_idempotence_exact_joins_failures_and_rollback(model):
    from psycopg import sql
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated.official import DDL, SourceRejected, address, weekly
    from mcp_open_data_hk.curated.official_ingest import save_capture, promote, rollback
    from mcp_open_data_hk.curated.official_read import OfficialReader
    from pathlib import Path

    version, _, reader, role, owner = model
    local_accept(version, owner)
    fixtures = Path(__file__).parent / "fixtures" / "official"
    body = (fixtures / "weekly-local.csv").read_bytes()
    key = "weekly:test"

    def parse(body):
        return weekly(body, "local", "20261012")

    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        conn.execute(DDL)
        capture, rows = save_capture(
            conn, key, "https://www.cr.gov.hk/test.csv", body, {}, parser=parse
        )
        repeated, _ = save_capture(
            conn, key, "https://www.cr.gov.hk/test.csv", body, {}, parser=parse
        )
        assert capture == repeated
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_records"
            ).fetchone()["n"]
            == 3
        )
        v1 = promote(conn, {key: capture}, {"view": "latest_observed"})
        assert promote(conn, {key: capture}, {"view": "latest_observed"}) == v1
        conn.execute(
            __import__("psycopg")
            .sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA curated TO {}")
            .format(sql.Identifier(role))
        )
        official = OfficialReader(reader)
        first = official.search(name="10", limit=1)
        assert first["nextCursor"]
        assert (
            official.search(namespace="cr:local:brn", value="81363340")["data"][0][
                "entity_id"
            ]
            == "cr:local:81363340"
        )
        assert (
            official.search(namespace="cr:local:brn", value="081363340")["data"] == []
        )
        assert (
            official.search(namespace="cr:foreign:brn", value="81363340")["data"] == []
        )
        with pytest.raises(SourceRejected):
            save_capture(
                conn, key, "https://www.cr.gov.hk/test.csv", body[:-8], {}, parser=parse
            )
        assert official.search(name="10")["version"] == v1
        shortened = b"\n".join(body.splitlines()[:2]) + b"\n"
        with pytest.raises(SourceRejected, match="COMPLETENESS"):
            save_capture(
                conn, key, "https://www.cr.gov.hk/test.csv", shortened, {}, parser=parse
            )
        assert official.search(name="10")["version"] == v1
        with pytest.raises(SourceRejected):
            promote(conn, {key: "unvalidated"}, {})
        assert official.search(name="10")["version"] == v1
        brn = rows[0]["identifier"]["value"]
        addr = (fixtures / "local.json").read_bytes()
        address_id, _ = save_capture(
            conn,
            "address:test",
            "https://data.cr.gov.hk/test",
            addr,
            {},
            parser=lambda b: address(b, "local", brn),
        )
        v2 = promote(
            conn,
            {key: capture, "address:test": address_id},
            {"view": "latest_observed"},
        )
        assert v2 != v1
        assert len(official.get("cr:local:" + brn, v2)["data"]["observations"]) == 2
        assert len(official.get("cr:local:" + brn, v1)["data"]["observations"]) == 1
        second = official.search(name="10", limit=1, cursor=first["nextCursor"])
        assert second["version"] == v1 and second["data"] != first["data"]
        rollback(conn, v1)
        assert official.search(name="10")["version"] == v1
        assert official.get("cr:local:" + brn, v2)["version"] == v2
        with pytest.raises(ReadError):
            official.get("81363340")
        with pytest.raises(ReadError):
            official.search(name="wrong", cursor=first["nextCursor"])
        assert reader.get(1)["version"] == version
