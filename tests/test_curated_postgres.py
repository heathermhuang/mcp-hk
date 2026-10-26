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
            from mcp_open_data_hk.curated import official_state as state

            state.begin_job(source, "backfill", "2026-10-24T12:20:00Z")
            state.reserve(source)
            state.stage_group(source, "restore-fixture", {"restore-fixture": capture})
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
        with (
            connect(source_dsn, row_factory=dict_row) as original_conn,
            connect(restore_dsn, row_factory=dict_row) as restored_conn,
        ):
            for table in [
                "official_jobs",
                "official_daily_budgets",
                "official_staged",
                "official_source_state",
            ]:
                query = sql.SQL(
                    "SELECT md5(coalesce(string_agg(row_to_json(t)::text,E'\\n' ORDER BY row_to_json(t)::text),'')) AS sha FROM curated.{} t"
                ).format(sql.Identifier(table))
                assert (
                    original_conn.execute(query).fetchone()
                    == restored_conn.execute(query).fetchone()
                )
        from mcp_open_data_hk.curated.official_recovery import snapshot

        with (
            connect(source_dsn, row_factory=dict_row) as original_conn,
            connect(restore_dsn, row_factory=dict_row) as restored_conn,
        ):
            assert snapshot(original_conn) == snapshot(restored_conn)
            expected_recovery = snapshot(restored_conn)
        from mcp_open_data_hk.curated.official_restore_check import (
            verify as verify_restored,
        )

        restored_proof = verify_restored(
            restore_dsn,
            expected_recovery,
            {
                "prefix": "curated/official/daily/20261024T130000Z-1234abcd",
                "artifacts": {"official.dump": {"sha256": proof["sha256"]}},
            },
        )
        assert (
            restored_proof["performancePassed"]
            and restored_proof["rawCaptureChecksumsVerified"] == 1
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
    cases.append(
        (
            "/api/v1/companies",
            {"q": "foo", "groupBy": "organisation"},
            "hk_company_search",
            {"q": "foo", "groupBy": "organisation"},
        )
    )
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
        grouped = official.search(name="10", groupBy="organisation", limit=1)
        assert grouped["groupBy"] == "organisation"
        assert len(grouped["data"][0]["matched_names"]) <= 3
        assert grouped["data"][0]["matched_fact_count"] >= 1
        grouped_next = official.search(
            name="10", groupBy="organisation", limit=1, cursor=grouped["nextCursor"]
        )
        assert grouped_next["data"][0]["entity_id"] != grouped["data"][0]["entity_id"]
        with pytest.raises(ReadError, match="does not match"):
            official.search(name="10", cursor=grouped["nextCursor"])
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


def test_official_maintenance_budgets_occurrences_transform_and_conflicts(
    model, monkeypatch
):
    from pathlib import Path
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_ingest as ingest
    from mcp_open_data_hk.curated.official import SourceRejected, weekly

    _, _, _, _, owner = model
    body = (Path(__file__).parent / "fixtures/official/weekly-local.csv").read_bytes()
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        state.migrate(conn)
        stamp = "2026-10-25T05:00:00Z"
        job = state.begin_job(conn, "backfill", stamp)
        assert job
        assert state.begin_job(conn, "backfill", "2026-10-25T13:00:00+08:00") is None
        assert state.begin_job(conn, "addresses", stamp)
        token = state.reserve(conn)
        # Unknown request is never refunded; a later successful read settles only itself.
        state.settle_bytes(conn, state.reserve(conn), 12)
        row = conn.execute("SELECT * FROM curated.official_daily_budgets").fetchone()
        assert row["requests"] == 2 and row["bytes"] == token[0] + 12
        conn.execute("UPDATE curated.official_daily_budgets SET requests=500")
        with pytest.raises(SourceRejected, match="DAILY_SOURCE_BUDGET"):
            state.reserve(conn)
        state.hold(conn, 3600)
        assert json.loads(json.dumps(state.plan(conn)))["sourceHoldUntil"]
        with pytest.raises(SourceRejected, match="SOURCE_HOLD"):
            state.reserve(conn)

        def parse(b):
            return weekly(b, "local", "20261012")

        cap, _ = ingest.save_capture(
            conn, "test", "https://www.cr.gov.hk/test.csv", body, {}, parser=parse
        )
        assert (
            cap
            == ingest.save_capture(
                conn, "test", "https://www.cr.gov.hk/test.csv", body, {}, parser=parse
            )[0]
        )
        monkeypatch.setattr(state, "transform_hash", lambda: "b" * 64)
        replay, _ = ingest.save_capture(
            conn, "test", "https://www.cr.gov.hk/test.csv", body, {}, parser=parse
        )
        assert replay != cap
        assert (
            conn.execute(
                "SELECT count(DISTINCT sha256) AS n FROM curated.official_captures"
            ).fetchone()["n"]
            == 1
        )
        v1 = ingest.promote(conn, {"test": cap}, {}, expected_base=None)
        v2 = ingest.promote(conn, {"test": replay}, {}, expected_base=v1)
        with pytest.raises(SourceRejected, match="PUBLICATION_CONFLICT"):
            ingest.promote(conn, {"test": cap}, {}, expected_base=v1)
        assert state.pointer(conn) == v2
        with connect(owner, autocommit=True, row_factory=dict_row) as contender:
            conn.execute("SELECT pg_advisory_lock(%s)", (state.LOCK,))
            assert ingest.run(owner, mode="backfill")["status"] == "busy"
            conn.execute("SELECT pg_advisory_unlock(%s)", (state.LOCK,))
            assert state.pointer(contender) == v2


def test_official_backfill_stages_complete_pairs_and_resumes_without_daily_reads(
    model, monkeypatch
):
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_ingest as ingest
    from mcp_open_data_hk.curated.official import SourceRejected

    _, _, _, _, owner = model
    base = "https://www.cr.gov.hk/docs/wrpt/RNC063/RNC063"
    links = [
        base + s + "_" + w + ".csv"
        for w in ["20250106", "20250113", "20250120", "20250127", "20250203"]
        for s in ["L", "F"]
    ]
    seen = []

    class Fake:
        requests = 0
        bytes = 0
        checks = []

        def get(self, url):
            self.requests += 1
            seen.append(url)
            if "F_20250113" in url:
                raise SourceRejected("FIXTURE_FAILED_REGISTER")
            return b"fixture", {}

        def close(self):
            pass

    def capture(conn, key, url, body, headers, verification, parser):
        cap = __import__("hashlib").sha256(key.encode()).hexdigest()
        conn.execute(
            "INSERT INTO curated.official_captures(capture_id,source_key,sha256,body,receipt,valid) VALUES(%s,%s,%s,%s,'{}',true) ON CONFLICT DO NOTHING",
            (cap, key, cap, body),
        )
        return cap, []

    monkeypatch.setattr(ingest, "save_capture", capture)
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        state.inventory(conn, links, "a" * 64)
    first = ingest.run(
        owner, Fake(), mode="backfill", scheduled_for="2026-10-24T12:20:00Z"
    )
    assert first["status"] == "partial"
    assert first["requests"] <= 16
    assert first["inventory"]["stagedFiles"] == 6
    assert first["inventory"]["downloadedFiles"] == 6
    assert first["inventory"]["discoveredFiles"] == 10
    assert first["inventory"]["rejectedFiles"] == 0
    assert first["inventory"]["publishedFiles"] == 0
    assert all("/wrpt/" in url for url in seen)
    seen.clear()
    second = ingest.run(
        owner, Fake(), mode="backfill", scheduled_for="2026-10-24T14:20:00Z"
    )
    assert second["inventory"]["stagedFiles"] == 8
    assert not any("20250106" in url for url in seen)
    duplicate = ingest.run(
        owner, Fake(), mode="backfill", scheduled_for="2026-10-24T14:20:00Z"
    )
    assert duplicate["status"] == "duplicate"
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        assert state.pointer(conn) is None
        # Missing catalogue entries remain recorded; absence never deletes captures.
        state.inventory(conn, links[2:], "b" * 64)
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_inventory WHERE NOT present"
            ).fetchone()["n"]
            == 2
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_staged"
            ).fetchone()["n"]
            == 8
        )


def test_official_address_a_b_b_history_queue_growth_and_health(model, monkeypatch):
    from pathlib import Path
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_ingest as ingest
    from mcp_open_data_hk.curated import official_health as health
    from mcp_open_data_hk.curated.official import weekly

    _, _, reader, role, owner = model
    fixtures = Path(__file__).parent / "fixtures/official"
    body = (fixtures / "weekly-local.csv").read_bytes()
    address_a = json.loads((fixtures / "local.json").read_bytes())
    entity = "cr:local:" + address_a[0]["Brn"]
    address_b = json.loads(json.dumps(address_a))
    address_b[0]["Address_of_Registered_Office"] = "SYNTHETIC ADDRESS B"

    class Fake:
        requests = 0
        bytes = 0
        checks = []

        def __init__(self, value):
            self.value = json.dumps(value).encode()

        def get(self, url, params):
            self.requests += 1
            return self.value, {}

    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        cap, _ = ingest.save_capture(
            conn,
            "test",
            "https://www.cr.gov.hk/test.csv",
            body,
            {},
            parser=lambda b: weekly(b, "local", "20261012"),
        )
        ingest.promote(conn, {"test": cap}, {})
        state.seed_queue(conn)
        conn.execute(
            "UPDATE curated.official_address_queue SET next_due=now()+interval '1 year' WHERE entity_id<>%s",
            (entity,),
        )
        for i, value in enumerate(
            [address_a, address_b, address_b, address_a, address_a]
        ):
            job = state.begin_job(conn, "addresses", f"2026-10-{24+i}T01:00:00Z")
            conn.execute(
                "UPDATE curated.official_address_queue SET next_due='-infinity' WHERE entity_id=%s",
                (entity,),
            )
            assert not ingest.collect_addresses(conn, Fake(value), job, 1)
            if i == 2:
                members = ingest.current_members(conn)
                members.update(
                    {
                        r["source_key"]: r["capture_id"]
                        for r in conn.execute("SELECT * FROM curated.official_staged")
                    }
                )
                version_b = ingest.promote(conn, members, {})
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_address_checks"
            ).fetchone()["n"]
            == 5
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_staged WHERE group_key=%s",
                ("address:" + entity,),
            ).fetchone()["n"]
            == 3
        )
        from psycopg import sql
        from mcp_open_data_hk.curated.official_read import OfficialReader

        members = ingest.current_members(conn)
        members.update(
            {
                r["source_key"]: r["capture_id"]
                for r in conn.execute("SELECT * FROM curated.official_staged")
            }
        )
        version_a = ingest.promote(conn, members, {})
        conn.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA curated TO {}").format(
                sql.Identifier(role)
            )
        )
        official = OfficialReader(reader)
        assert (
            official.get(entity, version_b)["data"]["latestAddress"]["address"]
            == "SYNTHETIC ADDRESS B"
        )
        assert (
            official.get(entity, version_a)["data"]["latestAddress"]["address"]
            == address_a[0]["Address_of_Registered_Office"]
        )
        page = official.address_history(entity, limit=1, version=version_a)
        assert (
            page["nextCursor"]
            and page["data"][0]["address"]
            == address_a[0]["Address_of_Registered_Office"]
        )
        ingest.rollback(conn, version_b)
        page2 = official.address_history(entity, limit=1, cursor=page["nextCursor"])
        assert (
            page2["version"] == version_a
            and page2["data"][0]["address"] == "SYNTHETIC ADDRESS B"
        )
        with pytest.raises(Exception, match="Cursor"):
            official.address_history(
                entity, version=version_b, cursor=page["nextCursor"]
            )
        old_capture = conn.execute(
            "SELECT latest_capture FROM curated.official_address_queue WHERE entity_id=%s",
            (entity,),
        ).fetchone()["latest_capture"]
        monkeypatch.setattr(state, "transform_hash", lambda: "f" * 64)
        conn.execute(
            "UPDATE curated.official_address_queue SET next_due='-infinity' WHERE entity_id=%s",
            (entity,),
        )
        replay_job = state.begin_job(conn, "addresses", "2026-10-29T01:00:00Z")
        assert not ingest.collect_addresses(conn, Fake(address_a), replay_job, 1)
        new_capture = conn.execute(
            "SELECT latest_capture FROM curated.official_address_queue WHERE entity_id=%s",
            (entity,),
        ).fetchone()["latest_capture"]
        assert new_capture != old_capture
        queue = conn.execute(
            "SELECT * FROM curated.official_address_queue WHERE entity_id=%s", (entity,)
        ).fetchone()
        # A true no-match and an interrupted request preserve every prior fact.
        from mcp_open_data_hk.curated.official import SourceRejected
        from mcp_open_data_hk.curated.official_address_stage import usage

        class NoMatch(Fake):
            def get(self, url, params):
                raise SourceRejected("SOURCE_NO_MATCH")

        class Interrupted(Fake):
            def get(self, url, params):
                raise RuntimeError("simulated process interruption")

        for day, source in [(30, NoMatch(address_a)), (31, Interrupted(address_a))]:
            conn.execute(
                "UPDATE curated.official_address_queue SET next_due='-infinity' WHERE entity_id=%s",
                (entity,),
            )
            job = state.begin_job(conn, "addresses", f"2026-10-{day}T01:00:00Z")
            before = usage(conn)["attempts"]
            if day == 30:
                assert (
                    ingest.collect_addresses(conn, source, job, 1)[0]["code"]
                    == "SOURCE_NO_MATCH"
                )
            else:
                with pytest.raises(RuntimeError, match="interruption"):
                    ingest.collect_addresses(conn, source, job, 1)
            retained = conn.execute(
                "SELECT * FROM curated.official_address_queue WHERE entity_id=%s",
                (entity,),
            ).fetchone()
            assert retained["last_success"] == queue["last_success"]
            assert retained["latest_capture"] == queue["latest_capture"]
            assert retained["latest_observation"] == queue["latest_observation"]
            assert usage(conn)["attempts"] == before + 1
        queue = retained
        state.seed_queue(conn)
        assert (
            conn.execute(
                "SELECT * FROM curated.official_address_queue WHERE entity_id=%s",
                (entity,),
            ).fetchone()
            == queue
        )
        job = state.begin_job(conn, "freshness", "2026-10-25T05:00:00Z")
        conn.execute(
            "UPDATE curated.official_jobs SET status='success',collection_status='success',publication_status='published',backup_status='local_failed',finished_at=now() WHERE job_id=%s",
            (job,),
        )
        assert health.check(conn, "2026-10-25T05:00:00Z")["status"] == "backup_failure"
        again = health.check(conn, "2026-10-25T05:00:00Z")
        assert again["unchanged"] and again["status"] == "backup_failure"
        conn.execute(
            "UPDATE curated.official_jobs SET backup_status='local_verified' WHERE job_id=%s",
            (job,),
        )
        assert (
            health.check(conn, "2026-10-25T05:00:00Z")["status"]
            == "offsite_recovery_unqualified"
        )
        assert health.check(conn, "2026-10-26T05:00:00Z")["status"] == "missed"


def test_official_publication_and_job_receipt_are_one_transaction(model, monkeypatch):
    from pathlib import Path
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_ingest as ingest
    from mcp_open_data_hk.curated.official import weekly

    _, _, _, _, owner = model
    body = (Path(__file__).parent / "fixtures/official/weekly-local.csv").read_bytes()
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        cap, _ = ingest.save_capture(
            conn,
            "test",
            "https://www.cr.gov.hk/test.csv",
            body,
            {},
            parser=lambda b: weekly(b, "local", "20261012"),
        )
        first = ingest.promote(conn, {"test": cap}, {})
        conn.execute(
            "UPDATE curated.official_versions SET created_at=now()-interval '1 day'"
        )
        monkeypatch.setattr(state, "transform_hash", lambda: "c" * 64)
        replay, _ = ingest.save_capture(
            conn,
            "test",
            "https://www.cr.gov.hk/test.csv",
            body,
            {},
            parser=lambda b: weekly(b, "local", "20261012"),
        )
        state.stage_group(conn, "test", {"test": replay})
    original = state.finish_job

    def fail_published(conn, job_id, receipt):
        if receipt.get("published"):
            raise RuntimeError("Fixture receipt storage failure")
        return original(conn, job_id, receipt)

    monkeypatch.setattr(state, "finish_job", fail_published)
    failed = ingest.run(owner, mode="publish", scheduled_for="2026-10-24T05:00:00Z")
    assert failed["status"] == "failed"
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        assert state.pointer(conn) == first
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM curated.official_versions"
            ).fetchone()["n"]
            == 1
        )
        assert (
            conn.execute("SELECT capture_id FROM curated.official_staged").fetchone()[
                "capture_id"
            ]
            == replay
        )
    monkeypatch.setattr(state, "finish_job", original)
    passed = ingest.run(owner, mode="publish", scheduled_for="2026-10-25T05:00:00Z")
    assert passed["published"] and passed["status"] == "success"
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        assert state.pointer(conn) == passed["version"]
        assert (
            conn.execute(
                "SELECT publication_status FROM curated.official_jobs WHERE job_id=%s",
                (passed["jobId"],),
            ).fetchone()["publication_status"]
            == "published"
        )


def test_address_cohort_clock_and_persisted_turns_prevent_backlog_starvation(model):
    from datetime import datetime, timedelta, timezone
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated.official_address_queue import targets

    _, _, _, _, owner = model
    clock = datetime(2026, 10, 26, tzinfo=timezone.utc)
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        for i in range(20):
            conn.execute(
                "INSERT INTO curated.official_address_queue(entity_id) VALUES(%s)",
                (f"initial:{i:03}",),
            )
        conn.execute(
            "INSERT INTO curated.official_address_queue(entity_id,last_success,next_due) VALUES('refresh',%s,%s)",
            (clock - timedelta(days=90), clock),
        )
        conn.execute(
            "INSERT INTO curated.official_address_queue(entity_id,priority,next_due) VALUES('priority',true,%s)",
            (clock + timedelta(days=1),),
        )
        chosen = []
        for _ in range(5):
            target = targets(conn, 1, at=clock)[0]
            chosen.append(target)
            conn.execute(
                "UPDATE curated.official_address_queue SET next_due=%s,last_attempt=%s WHERE entity_id=%s",
                (clock + timedelta(days=1), clock, target["entity_id"]),
            )
            conn.execute(
                "INSERT INTO curated.official_source_state(family,state) VALUES('address_scheduler',%s) ON CONFLICT(family) DO UPDATE SET state=EXCLUDED.state",
                (Jsonb({"offset": target["next_offset"]}),),
            )
        assert any(t["entity_id"] == "refresh" for t in chosen)
        assert all(t["entity_id"] != "priority" for t in chosen)
        assert "priority" in {
            target["entity_id"]
            for target in targets(conn, 10, at=clock + timedelta(days=1))
        }


def test_official_offsite_job_failure_retains_last_copy_and_holds_growth(model):
    from datetime import datetime, timezone
    from psycopg.rows import dict_row
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_offsite_job as recovery

    _, _, _, _, owner = model
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        job = state.begin_job(
            conn, "offsite", "2026-10-24T13:30:00Z", family="recovery"
        )
        receipt = {
            "prefix": "curated/official/daily/20261024T133000Z-1234abcd",
            "artifacts": {
                name: {"sha256": "a" * 64, "bytes": 10}
                for name in ["official.dump", "source.json", "manifest.json"]
            },
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
        }
        with pytest.raises(ValueError, match="Unqualified"):
            recovery.finish(
                conn,
                job,
                dict(receipt, prefix="backups/legacy"),
                "offsite_verified",
                "qualification",
            )
        recovery.finish(conn, job, receipt, "offsite_verified", "qualification")
        assert not recovery.gate(conn)
        migrations = {
            r["version"]: r["sha256"]
            for r in conn.execute(
                "SELECT version,sha256 FROM curated.official_migrations"
            )
        }
        proof = {
            "freshOffsiteRestoreVerified": True,
            "backupSha256": "a" * 64,
            "prefix": receipt["prefix"],
            "migrations": migrations,
            "performancePassed": True,
            "qualifiedWeekPairs": 4,
            "stagedReadP95Ms": 100,
        }
        with pytest.raises(ValueError, match="exact"):
            recovery.qualify_restore(conn, dict(proof, backupSha256="b" * 64))
        assert not recovery.gate(conn)
        with pytest.raises(ValueError, match="schema"):
            recovery.qualify_restore(conn, dict(proof, migrations={}))
        recovery.qualify_restore(conn, proof)
        assert recovery.gate(conn)
        failure = state.begin_job(
            conn, "offsite", "2026-10-25T05:17:00Z", family="recovery"
        )
        recovery.finish(
            conn,
            failure,
            {"errorCode": "OFFSITE_UPLOAD_OR_BACKUP_FAILED"},
            "offsite_failed",
            "daily",
        )
        assert not recovery.gate(conn)
        stored = conn.execute(
            "SELECT state FROM curated.official_source_state WHERE family='offsite'"
        ).fetchone()["state"]
        assert stored["lastSuccess"]["prefix"] == receipt["prefix"]
        assert stored["lastAttempt"]["status"] == "offsite_failed"
        with pytest.raises(ValueError, match="owning"):
            recovery.finish(conn, job, receipt, "offsite_verified", "qualification")
        older = state.begin_job(
            conn, "offsite", "2026-10-26T05:17:00Z", family="recovery"
        )
        newer = state.begin_job(
            conn, "offsite", "2026-10-27T05:17:00Z", family="recovery"
        )
        receipt_new = dict(
            receipt, prefix="curated/official/daily/20261027T051700Z-5678abcd"
        )
        recovery.finish(conn, newer, receipt_new, "offsite_verified", "daily")
        recovery.finish(
            conn, older, {"errorCode": "OLDER_FAILURE"}, "offsite_failed", "daily"
        )
        stored = conn.execute(
            "SELECT state FROM curated.official_source_state WHERE family='offsite'"
        ).fetchone()["state"]
        assert stored["lastSuccess"]["prefix"] == receipt_new["prefix"]
        assert stored["lastAttempt"]["jobId"] == newer
        assert not recovery.gate(conn)
        recovery.qualify_restore(conn, dict(proof, prefix=receipt_new["prefix"]))
        assert recovery.gate(conn)


def test_official_address_stages_count_legacy_and_require_enlarged_restore(
    model, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from mcp_open_data_hk.curated import official_state as state
    from mcp_open_data_hk.curated import official_address_stage as policy
    from mcp_open_data_hk.curated.official import SourceRejected

    _, _, _, _, owner = model
    url = "https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/local/search"
    with connect(owner, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        conn.execute(
            "INSERT INTO curated.official_runs(run_id,status,receipt) VALUES('legacy','success',%s)",
            (
                Jsonb(
                    {
                        "sourceChecks": [{"sourceUrl": url} for _ in range(20)],
                        "addressFailures": [{"code": "SOURCE_NO_MATCH"}],
                    }
                ),
            ),
        )
        job = state.begin_job(conn, "addresses", "2026-10-24T01:00:00Z")
        for i in range(20):
            conn.execute(
                "INSERT INTO curated.official_address_checks(job_id,entity_id,outcome) VALUES(%s,%s,%s)",
                (job, "cr:local:" + str(i), "SOURCE_NO_MATCH" if i == 0 else "success"),
            )
        assert (
            policy.usage(conn)["attempts"] == 40
            and policy.usage(conn)["remaining"] == 0
        )
        monkeypatch.setattr(policy, "gate", lambda c: False)
        with pytest.raises(SourceRejected, match="RECOVERY"):
            policy.set_stage(conn, 100)
        monkeypatch.setattr(policy, "gate", lambda c: True)
        policy.set_stage(conn, 100)
        assert policy.usage(conn)["remaining"] == 60
        with pytest.raises(SourceRejected, match="PILOT"):
            policy.set_stage(conn, 250)
        for i in range(20, 80):
            conn.execute(
                "INSERT INTO curated.official_address_checks(job_id,entity_id,outcome) VALUES(%s,%s,'success')",
                (job, "cr:local:" + str(i)),
            )
        conn.execute(
            "UPDATE curated.official_jobs SET status='success',receipt=%s WHERE job_id=%s",
            (
                Jsonb(
                    {
                        "sourceChecks": [
                            {"sourceUrl": url, "durationSeconds": 1} for _ in range(60)
                        ],
                        "maxRssKiB": 100000,
                    }
                ),
                job,
            ),
        )
        with pytest.raises(SourceRejected, match="RESTORE"):
            policy.set_stage(conn, 250)
        conn.execute(
            "INSERT INTO curated.official_source_state(family,state) VALUES('offsite_restore',%s)",
            (
                Jsonb(
                    {
                        "verifiedAt": (
                            datetime.now(timezone.utc) + timedelta(seconds=1)
                        ).isoformat()
                    }
                ),
            ),
        )
        policy.set_stage(conn, 250)
        assert policy.usage(conn)["remaining"] == 150
        assert state.pointer(conn) is None


def test_grouped_search_bounds_aliases_before_pagination_and_binds_cursor(model):
    from psycopg import sql

    version, manifest, reader, role, owner = model
    # More matching facts than a page; two source entities keep identical names.
    with connect(owner) as conn:
        conn.execute(
            sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(
                sql.Identifier(schema_name(version))
            )
        )
        for n in range(25):
            conn.execute(
                "INSERT INTO entity_names(fact_id,entity_id,language,display_name,search_key,name_kind,until_precision) VALUES(%s,1,'en','Foo shared',%s,'former_name','unknown')",
                (f"alias-{n:03}", f"foo alias {n:03}"),
            )
        conn.execute(
            "INSERT INTO entity_names(fact_id,entity_id,language,display_name,search_key,name_kind,until_precision) VALUES('same-name',2,'en','Foo shared','foo shared','former_name','unknown')"
        )
    local_accept(version, owner)
    first = reader.search(name="foo", groupBy="organisation", limit=1)
    assert first["groupBy"] == "organisation"
    assert first["data"][0]["entity_id"] == 1
    assert first["data"][0]["matched_fact_count"] == 27
    assert len(first["data"][0]["matched_names"]) == 3
    second = reader.search(
        name="foo", groupBy="organisation", limit=1, cursor=first["nextCursor"]
    )
    assert second["data"][0]["entity_id"] == 2
    assert second["nextCursor"] is None
    assert {
        r["display_name"] for r in reader.related(1, "names", limit=100)["data"]
    } >= {"Foo shared"}
    assert len(reader.search(name="foo")["data"]) == 20  # default is still name facts
    with pytest.raises(ReadError, match="does not match"):
        reader.search(name="foo", cursor=first["nextCursor"])
    with pytest.raises(ReadError, match="at most 20"):
        reader.search(name="foo", groupBy="organisation", limit=21)
    exact = reader.search(
        namespace="webb:incorporation:1", value="0000123", groupBy="organisation"
    )
    assert exact["data"][0]["entity_id"] == 1
    assert not reader.search(
        namespace="webb:incorporation:1", value="123", groupBy="organisation"
    )["data"]
