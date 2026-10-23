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
        proof = backup(container, original, version, tmp_path / "model.dump")
        with pytest.raises(ValueError, match="checksum"):
            restore(container, restored, tmp_path / "model.dump", "0" * 64)
        restore(container, restored, tmp_path / "model.dump", proof["sha256"])
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
