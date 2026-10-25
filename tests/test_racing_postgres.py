"""Real PostgreSQL source isolation, policy races, durable budgets and full restore."""

import hashlib
import os
import subprocess
import uuid
from datetime import datetime, timezone

import httpx
import pytest

from racing_support import source_policy, bundle, ROUTE
from mcp_open_data_hk.curated.racing.db import connect
from mcp_open_data_hk.curated.racing import store
from mcp_open_data_hk.curated.racing.collector import Collector
from mcp_open_data_hk.curated.racing.policy import RacingRejected
from mcp_open_data_hk.curated.racing.read import RacingReader, grant_reader
from mcp_open_data_hk.curated.read import Reader, ReadError

DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated PostgreSQL lane runs racing contracts",
)


@pytest.fixture
def db():
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    assert DSN
    token = uuid.uuid4().hex[:10]
    database, restored, role = (
        "race_" + token,
        "race_restore_" + token,
        "race_reader_" + token,
    )
    config = conninfo_to_dict(DSN)
    owner = make_conninfo(**dict(config, dbname=database))
    target = make_conninfo(**dict(config, dbname=restored))
    with connect(DSN, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored)))
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    try:
        store.migrate(owner)
        digest = store.install_policy(owner, source_policy(), activate=True)
        yield owner, target, digest, role, config
    finally:
        with connect(DSN, autocommit=True) as conn:
            for name in (database, restored):
                conn.execute(
                    sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                        sql.Identifier(name)
                    )
                )
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def settle_cadence(owner):
    with connect(owner) as conn:
        conn.execute(
            "UPDATE racing.requests SET reserved_at=reserved_at-interval '2 seconds'"
        )


def test_migration_idempotence_mixed_order_and_reader_isolation(db):
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    owner, _, digest, role, config = db
    store.migrate(owner)
    with connect(owner) as conn:
        from mcp_open_data_hk.curated.official_state import migrate as official_migrate

        official_migrate(conn)
        conn.execute("CREATE SCHEMA sfc; CREATE TABLE sfc.protected(id int)")
    store.migrate(owner)
    grant_reader(owner, role)
    from psycopg.conninfo import conninfo_to_dict

    serving = dict(conninfo_to_dict(owner), user=role)
    serving.pop("password", None)
    with connect(make_conninfo(**serving)) as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM racing.races").fetchone()["n"] == 0
        )
        with pytest.raises(Exception, match="permission denied"):
            conn.execute("INSERT INTO racing.races(version,race_id) VALUES('x','y')")
    with connect(owner) as conn:
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA racing TO {}").format(sql.Identifier(role))
        )
    manifest, tables = bundle(digest)
    store.stage(owner, "v1", digest, manifest, tables)
    with connect(owner) as conn:
        with pytest.raises(Exception, match="IMMUTABLE"):
            conn.execute("DELETE FROM racing.results WHERE version='v1'")


def test_full_backup_restore_cas_revoke_and_synthetic_read_gate(db, tmp_path):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    owner, target, digest, role, config = db
    manifest, tables = bundle(digest)
    expected = store.stage(owner, "v1", digest, manifest, tables)
    assert expected["results"]["rows"] == 2 and expected["runners"]["rows"] == 2
    container = os.environ.get("CURATED_TEST_CONTAINER")
    assert container, "Real racing restore requires the dedicated PostgreSQL container"
    database, restored = (
        conninfo_to_dict(owner)["dbname"],
        conninfo_to_dict(target)["dbname"],
    )
    artifact = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "pg_dump",
            "-U",
            "postgres",
            "-d",
            database,
            "-Fc",
            "--schema=racing",
            "--no-owner",
            "--no-acl",
        ],
        check=True,
        capture_output=True,
    ).stdout
    backup = tmp_path / "racing.dump"
    backup.write_bytes(artifact)
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
            restored,
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
        ],
        input=backup.read_bytes(),
        check=True,
        capture_output=True,
    )
    proof = store.qualify_restore(
        owner, target, "v1", hashlib.sha256(artifact).hexdigest()
    )
    assert proof["tables"] == expected
    with pytest.raises(RacingRejected, match="INDEPENDENT"):
        store.qualify_restore(owner, owner, "v1", "a" * 64)
    store.publish(owner, "v1", expected=None)
    with pytest.raises(RacingRejected, match="CONFLICT"):
        store.publish(owner, "v1", expected=None)
    grant_reader(owner, role)
    serving = dict(conninfo_to_dict(owner), user=role)
    serving.pop("password", None)
    reader = RacingReader(
        Reader(make_conninfo(**serving), b"synthetic-cursor-secret-at-least-32-bytes")
    )
    with pytest.raises(ReadError, match="Synthetic"):
        reader.page("races")
    store.revoke(owner, digest)
    with pytest.raises(RacingRejected, match="INACTIVE"):
        store.publish(owner, "v1", expected="v1")
    with connect(owner) as conn:
        assert (
            conn.execute("SELECT version FROM racing.accepted").fetchone()["version"]
            == "v1"
        )


def test_collector_disabled_duplicate_reservations_and_revocation(db):
    owner, _, digest, _, _ = db
    calls = []

    def handle(request):
        calls.append(request.url)
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"synthetic only"
        )

    transport = httpx.MockTransport(handle)
    with pytest.raises(RacingRejected, match="DISABLED"):
        Collector(owner, digest, transport=transport).run(
            "meeting", "2026-01-01T00:00:00Z", [("results", ROUTE)]
        )
    assert calls == []
    collector = Collector(owner, digest, transport=transport, enabled=True)
    result = collector.run("meeting", "2026-01-01T00:00:00Z", [("results", ROUTE)])
    assert result["state"] == "complete" and len(calls) == 1
    assert (
        collector.run("meeting", "2026-01-01T00:00:00Z", [("results", ROUTE)])["state"]
        == "duplicate"
    )
    settle_cadence(owner)

    def revoke_in_flight(request):
        store.revoke(owner, digest)
        return httpx.Response(
            200, headers={"content-type": "text/html"}, content=b"must withhold"
        )

    with pytest.raises(RacingRejected, match="INACTIVE"):
        Collector(
            owner, digest, transport=httpx.MockTransport(revoke_in_flight), enabled=True
        ).run("meeting", "2026-01-02T00:00:00Z", [("results", ROUTE)])
    with connect(owner) as conn:
        assert (
            conn.execute("SELECT attempts FROM racing.budgets").fetchone()["attempts"]
            == 2
        )
        assert (
            conn.execute("SELECT count(*) AS n FROM racing.requests").fetchone()["n"]
            == 2
        )


@pytest.mark.parametrize("status", [304, 403, 429, 503])
def test_provider_holds_persist_across_jobs_and_midnight(db, status):
    owner, _, digest, _, _ = db
    collector = Collector(
        owner,
        digest,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(status, headers={"Retry-After": "120"})
        ),
        enabled=True,
    )
    with pytest.raises(RacingRejected):
        collector.run("meeting", "2026-01-01T00:00:00Z", [("results", ROUTE)])
    with connect(owner) as conn:
        assert conn.execute("SELECT hold_until FROM racing.source_state").fetchone()[
            "hold_until"
        ] > datetime.now(timezone.utc)
    with pytest.raises(RacingRejected, match="UNRECONCILED_OR_HELD"):
        collector.run("meeting", "2026-01-02T00:00:00Z", [("results", ROUTE)])
    with connect(owner) as conn:
        assert (
            conn.execute("SELECT attempts FROM racing.budgets").fetchone()["attempts"]
            == 1
        )


def test_unknown_crash_reservation_blocks_fresh_job(db):
    owner, _, digest, _, _ = db

    def crash(request):
        raise httpx.ReadTimeout("private upstream detail")

    collector = Collector(
        owner, digest, transport=httpx.MockTransport(crash), enabled=True
    )
    with pytest.raises(httpx.ReadTimeout):
        collector.run("history", "2026-01-01T00:00:00Z", [("results", ROUTE)])
    settle_cadence(owner)
    with pytest.raises(RacingRejected, match="UNRECONCILED"):
        collector.run("history", "2026-01-02T00:00:00Z", [("results", ROUTE)])
    with connect(owner) as conn:
        row = conn.execute("SELECT outcome,settled_at FROM racing.requests").fetchone()
        assert row["outcome"] == "unknown" and row["settled_at"] is None


def test_parser_failure_never_changes_last_pointer(db):
    owner, _, digest, _, _ = db
    manifest, tables = bundle(digest)
    tables["results"][0]["placing_raw"] = "NEW_UNKNOWN_CODE"
    with pytest.raises(RacingRejected, match="UNKNOWN_RESULT_CODE"):
        store.stage(owner, "bad", digest, manifest, tables)
    with connect(owner) as conn:
        assert (
            conn.execute("SELECT count(*) AS n FROM racing.versions").fetchone()["n"]
            == 0
        )


def test_partial_checkpoint_binds_inventory_and_retained_capture(db):
    owner, _, digest, _, _ = db
    collector = Collector(
        owner,
        digest,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"retained synthetic bytes",
            )
        ),
        enabled=True,
    )
    requests = [("results", ROUTE), ("results", ROUTE)]
    first = collector.run("season", "2026-01-01T00:00:00Z", requests)
    assert first["state"] == "partial" and len(first["captures"]) == 1
    capture_id = first["captures"][0]["captureId"]
    assert collector.retained_capture(capture_id) == b"retained synthetic bytes"
    with connect(owner) as conn:
        checkpoint = conn.execute(
            "SELECT checkpoint FROM racing.jobs WHERE run_id=%s", (first["runId"],)
        ).fetchone()["checkpoint"]
    assert checkpoint["next"] == 1
    settle_cadence(owner)
    second = collector.run(
        "season", "2026-01-02T00:00:00Z", requests, checkpoint=checkpoint
    )
    assert second["state"] == "complete" and len(second["captures"]) == 1
    with pytest.raises(RacingRejected, match="CHECKPOINT_INVENTORY_MISMATCH"):
        collector.run(
            "season",
            "2026-01-03T00:00:00Z",
            [("profiles", ROUTE), ("results", ROUTE)],
            checkpoint=checkpoint,
        )
    store.revoke(owner, digest)
    with pytest.raises(RacingRejected, match="INACTIVE"):
        collector.retained_capture(capture_id)


def test_multi_meeting_and_season_inventory(db):
    import copy
    from mcp_open_data_hk.curated.racing.normalize import meeting, race

    owner, _, digest, _, _ = db
    manifest, tables = bundle(digest)
    old_mid, old_rid = (
        tables["meetings"][0]["meeting_id"],
        tables["races"][0]["race_id"],
    )
    mid, rid = meeting("2026-01-02", "ST"), race("2026-01-02", "ST", 1)
    for table in ("meetings", "races", "runners", "results", "coverage"):
        original = copy.deepcopy(tables[table])
        for row in original:
            for key, value in list(row.items()):
                if isinstance(value, str):
                    row[key] = value.replace(old_rid, rid).replace(old_mid, mid)
                elif isinstance(value, list):
                    row[key] = [
                        (
                            item.replace(old_rid, rid).replace(old_mid, mid)
                            if isinstance(item, str)
                            else item
                        )
                        for item in value
                    ]
            if table == "meetings":
                row["local_date"], row["venue"] = "2026-01-02", "ST"
            tables[table].append(row)
    tables["coverage"].append(
        {
            "family": "races",
            "scope": "season",
            "group_id": "2025-2026",
            "expected_ids": [old_mid, mid],
            "observed_ids": [old_mid, mid],
            "complete": True,
            "proof": {"inventoryRef": "independent synthetic season"},
        }
    )
    result = store.stage(owner, "season", digest, manifest, tables)
    assert result["races"]["rows"] == 2 and result["results"]["rows"] == 4


def test_internal_reader_decimal_cursor_policy_and_shared_slots(db):
    """Synthetic owned-DB setup tests reader behavior, never real source qualification."""
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    owner, _, _, role, _ = db
    record = source_policy()
    manifest, tables = bundle("placeholder")
    record["families"]["results"]["fields"] = sorted(tables["results"][0])
    digest = store.install_policy(owner, record, activate=True)
    manifest, tables = bundle(digest)
    # The public gateway's compile-time gate still rejects all data. This explicit
    # test-owned metadata is only to exercise the future private reader branch.
    manifest["synthetic"] = False
    store.stage(owner, "v1", digest, manifest, tables)
    with connect(owner) as conn:
        conn.execute(
            "UPDATE racing.versions SET state='restore-qualified',restore_proof='{}' WHERE version='v1'"
        )
    # Use a nonempty synthetic proof in this isolated setup, not an external receipt.
    with connect(owner) as conn:
        conn.execute(
            "UPDATE racing.versions SET restore_proof='{\"testOwnedOnly\":true}' WHERE version='v1'"
        )
    store.publish(owner, "v1", expected=None)
    grant_reader(owner, role)
    serving = dict(conninfo_to_dict(owner), user=role)
    serving.pop("password", None)
    base = Reader(
        make_conninfo(**serving), b"synthetic-cursor-secret-at-least-32-bytes"
    )
    reader = RacingReader(base)
    rid = tables["races"][0]["race_id"]
    first = reader.page("results", race_id=rid, limit=1)
    assert first["data"][0]["time_seconds"] == "69.23" and first["nextCursor"]
    second = reader.page(
        "results", race_id=rid, limit=1, cursor=first["nextCursor"], mode="mcp"
    )
    assert second["version"] == "v1" and second["data"][0]["status"] == "withdrawn"
    assert first["data"][0]["fact_id"] != second["data"][0]["fact_id"]
    with pytest.raises(ReadError, match="Cursor"):
        reader.page("results", race_id="different", cursor=first["nextCursor"])
    for _ in range(4):
        base.slots.acquire()
    try:
        with pytest.raises(ReadError, match="slots"):
            reader.page("results", race_id=rid)
    finally:
        for _ in range(4):
            base.slots.release()
    store.revoke(owner, digest)
    with pytest.raises(ReadError, match="policy"):
        reader.page("results", race_id=rid)


def test_expired_raw_bytes_erased_but_receipts_retained(db):
    from mcp_open_data_hk.curated.racing.maintenance import expire_raw

    owner, _, digest, _, _ = db
    collector = Collector(
        owner,
        digest,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"expiring synthetic bytes",
            )
        ),
        enabled=True,
    )
    result = collector.run("meeting", "2026-01-01T00:00:00Z", [("results", ROUTE)])
    capture_id = result["captures"][0]["captureId"]
    assert expire_raw(owner)["erasedBodies"] == 0
    with connect(owner) as conn:
        conn.execute(
            "UPDATE racing.capture_buffer SET expires_at=now()-interval '1 second' WHERE capture_id=%s",
            (capture_id,),
        )
    with pytest.raises(RacingRejected, match="CAPTURE_EXPIRED"):
        collector.retained_capture(capture_id)
    assert expire_raw(owner)["erasedBodies"] == 1
    with connect(owner) as conn:
        row = conn.execute(
            "SELECT body,raw_sha256,run_id FROM racing.capture_buffer WHERE capture_id=%s",
            (capture_id,),
        ).fetchone()
        assert (
            row["body"] is None
            and row["raw_sha256"]
            == hashlib.sha256(b"expiring synthetic bytes").hexdigest()
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM racing.requests WHERE run_id=%s",
                (row["run_id"],),
            ).fetchone()["n"]
            == 1
        )
