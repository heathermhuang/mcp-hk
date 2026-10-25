"""Mandatory real PostgreSQL SFC contracts; all facts/policies fabricated."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.read import Reader, ReadError
from mcp_open_data_hk.curated.sfc.contracts import Rejected
from mcp_open_data_hk.curated.sfc.state import State, grant_reader
from mcp_open_data_hk.curated.sfc.read import SfcReader
from test_sfc import fake_policy, fake_fact

DSN = os.environ.get("CURATED_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN and not os.environ.get("CURATED_REQUIRE_DB"),
    reason="Dedicated PostgreSQL lane runs SFC contracts",
)


@pytest.fixture
def model():
    assert DSN, "CURATED_REQUIRE_DB requires CURATED_TEST_DSN"
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    token = uuid.uuid4().hex[:10]
    database = "sfc_" + token
    role = "sfc_reader_" + token
    config = conninfo_to_dict(DSN)
    owner = make_conninfo(**dict(config, dbname=database))
    with connect(DSN, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        admin.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
    try:
        state = State(owner)
        state.migrate()
        state.migrate()
        policy = fake_policy()
        state.activate(policy, policy.sha256)
        serving = dict(config, dbname=database, user=role)
        serving.pop("password", None)
        grant_reader(owner, role)
        yield state, policy, SfcReader(
            Reader(make_conninfo(**serving), b"sfc-test-secret-at-least-32-bytes!"),
            policy,
        ), role
    finally:
        with connect(DSN, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def stage(state, policy, cohort=("ZZZ001",), scheduled=None):
    run, new = state.start(
        scheduled or datetime.now(timezone.utc), list(cohort), policy.sha256
    )
    assert new
    payloads = {}
    for ce in cohort:
        attempt = state.reserve(run, ce, "detail")
        state.settle(attempt, "ok")
        payloads[ce] = (json.dumps(fake_fact(ce)).encode(), attempt)
    version, sha = state.stage(run, payloads)
    return version, sha, run


def test_migration_no_sibling_dependency_and_source_writer_isolation(model):
    state, policy, reader, role = model
    from psycopg import sql
    from psycopg.errors import InsufficientPrivilege, ReadOnlySqlTransaction
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    with state.connection() as conn:
        conn.execute(
            "CREATE SCHEMA curated_racing; CREATE TABLE curated_racing.sibling(id int); CREATE SCHEMA curated_hkex; CREATE TABLE curated_hkex.sibling(id int)"
        )
    state.migrate()
    with connect(reader.reader.dsn) as conn:
        with pytest.raises((InsufficientPrivilege, ReadOnlySqlTransaction)):
            conn.execute("DELETE FROM curated_sfc.pointer")
    writer = "sfc_writer_" + uuid.uuid4().hex[:10]
    try:
        with state.connection() as conn:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(writer)))
            conn.execute(
                sql.SQL(
                    "GRANT USAGE ON SCHEMA curated_sfc TO {}; GRANT ALL ON ALL TABLES IN SCHEMA curated_sfc TO {}; GRANT ALL ON ALL SEQUENCES IN SCHEMA curated_sfc TO {}"
                ).format(*[sql.Identifier(writer)] * 3)
            )
        config = conninfo_to_dict(state.dsn)
        config.update(user=writer)
        config.pop("password", None)
        with connect(make_conninfo(**config), autocommit=True) as conn:
            conn.execute("SELECT count(*) FROM curated_sfc.runs")
            with pytest.raises(InsufficientPrivilege):
                conn.execute("INSERT INTO curated_racing.sibling VALUES(1)")
            with pytest.raises(InsufficientPrivilege):
                conn.execute("INSERT INTO curated_hkex.sibling VALUES(1)")
    finally:
        with state.connection() as conn:
            conn.execute(
                sql.SQL("DROP OWNED BY {}; DROP ROLE {}").format(
                    sql.Identifier(writer), sql.Identifier(writer)
                )
            )


def test_idempotency_concurrency_unknown_requests_and_partial_cohort(model):
    state, policy, reader, _ = model
    when = datetime.now(timezone.utc)
    run, new = state.start(when, ["ZZZ001", "ZZZ002"], policy.sha256)
    assert new
    assert state.start(when, ["ZZZ002", "ZZZ001"], policy.sha256) == (run, False)
    with pytest.raises(Rejected, match="CONFLICT"):
        state.start(when, ["ZZZ003"], policy.sha256)
    with state.session():
        with pytest.raises(Rejected, match="SESSION_BUSY"):
            with State(state.dsn).session():
                pass
    attempt = state.reserve(run, "ZZZ001", "session")
    with pytest.raises(Rejected, match="UNCERTAIN"):
        state.reserve(run, "ZZZ001", "detail")
    state.settle(attempt, "ok")
    raw = json.dumps(fake_fact()).encode()
    with pytest.raises(Rejected, match="INCOMPLETE"):
        state.stage(run, {"ZZZ001": (raw, attempt)})
    with state.connection() as c:
        assert (
            c.execute("SELECT requests FROM curated_sfc.budgets").fetchone()["requests"]
            == 1
        )
        assert (
            c.execute("SELECT reserved_bytes FROM curated_sfc.runs").fetchone()[
                "reserved_bytes"
            ]
            == 262144
        )
        assert not c.execute("SELECT * FROM curated_sfc.pointer").fetchone()


def test_all_request_classes_failures_caps_and_holds(model):
    state, policy, _, _ = model
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
    for i in range(25):
        a = state.reserve(run, "ZZZ001", ("session", "detail", "retry")[i % 3])
        state.settle(a, ("failed", "missing", "rejected", "not_modified")[i % 4])
    with pytest.raises(Rejected, match="RUN_BUDGET"):
        state.reserve(run, "ZZZ001", "detail")
    state.finish(run)
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
    a = state.reserve(run, "ZZZ001", "detail")
    state.settle(
        a, "rejected", hold_until=datetime.now(timezone.utc) + timedelta(hours=1)
    )
    with pytest.raises(Rejected, match="SOURCE_HOLD"):
        state.reserve(run, "ZZZ001", "retry")
    with state.connection() as c:
        assert (
            c.execute("SELECT requests FROM curated_sfc.budgets").fetchone()["requests"]
            == 26
        )
        assert not c.execute("SELECT * FROM curated_sfc.pointer").fetchone()


def test_stricter_provider_daily_byte_and_time_caps(model):
    state, policy, _, _ = model
    p = fake_policy(readsPerRun=2, readsPerDay=3, bytesPerRun=100, bytesPerDay=120)
    state.activate(p, p.sha256)
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], p.sha256)
    a = state.reserve(run, "ZZZ001", "session", 60)
    state.settle(a, "failed")
    with pytest.raises(Rejected, match="RUN_BUDGET"):
        state.reserve(run, "ZZZ001", "retry", 50)
    a = state.reserve(run, "ZZZ001", "retry", 40)
    state.settle(a, "failed")
    state.finish(run)
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], p.sha256)
    with pytest.raises(Rejected, match="DAY_BUDGET"):
        state.reserve(run, "ZZZ001", "detail", 21)
    a = state.reserve(run, "ZZZ001", "detail", 20)
    state.settle(a, "failed")
    with pytest.raises(Rejected, match="DAY_BUDGET"):
        state.reserve(run, "ZZZ001", "retry", 1)
    with state.connection() as c:
        c.execute(
            "UPDATE curated_sfc.runs SET started_at=now()-interval '11 minutes' WHERE run_id=%s",
            (run,),
        )
    with pytest.raises(Rejected, match="TIMEOUT"):
        state.reserve(run, "ZZZ001", "retry", 1)


def test_policy_revocation_during_run_and_before_read_publication(model):
    state, policy, reader, _ = model
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
    a = state.reserve(run, "ZZZ001", "detail")
    state.revoke(policy.sha256)
    state.settle(a, "failed")
    with pytest.raises(Rejected, match="POLICY_CHANGED"):
        state.reserve(run, "ZZZ001", "retry")
    with pytest.raises(ReadError):
        reader.verify("ZZZ001")
    with pytest.raises(Rejected):
        state.activate(policy, "0" * 64)


def test_physical_restore_every_fact_capture_control_and_pointer(model, tmp_path):
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo
    from mcp_open_data_hk.curated.backup import backup, restore

    state, policy, reader, role = model
    version, sha, run = stage(state, policy, ("ZZZ001", "ZZZ002"))
    with pytest.raises(Rejected, match="RESTORE_REQUIRED"):
        state.publish(version, None)
    config = conninfo_to_dict(state.dsn)
    restored_name = "sfc_restore_" + uuid.uuid4().hex[:10]
    target = State(make_conninfo(**dict(config, dbname=restored_name)))
    container = os.environ.get("CURATED_TEST_CONTAINER")
    assert container, "SFC physical restore requires owned test container"
    receipt = backup(container, config["dbname"], version, tmp_path / "sfc.dump")
    with connect(DSN, autocommit=True) as admin:
        admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_name))
        )
    try:
        restore(container, restored_name, tmp_path / "sfc.dump", receipt["sha256"])
        with pytest.raises(Rejected, match="ARTIFACT_DIFFERS"):
            state.qualify_restore(version, target, tmp_path / "sfc.dump", "0" * 64)
        with pytest.raises(Rejected, match="NOT_INDEPENDENT"):
            state.qualify_restore(
                version, state, tmp_path / "sfc.dump", receipt["sha256"]
            )
        with target.connection() as c:
            c.execute(
                "UPDATE curated_sfc.corporations SET fact=jsonb_set(fact,'{statusCode}','\"CHANGED\"') WHERE ce='ZZZ002'"
            )
        with pytest.raises(Rejected, match="RESTORE_DIFFERS"):
            state.qualify_restore(
                version, target, tmp_path / "sfc.dump", receipt["sha256"]
            )
        with target.connection() as c:
            c.execute(
                "UPDATE curated_sfc.corporations SET fact=jsonb_set(fact,'{statusCode}','\"SOURCE_ACTIVE\"') WHERE ce='ZZZ002'"
            )
        proof = state.qualify_restore(
            version, target, tmp_path / "sfc.dump", receipt["sha256"]
        )
        assert proof["factsSha256"] == sha
        assert state.facts(version) == target.facts(version)
        state.publish(version, None)
        found = reader.verify("zzz001", version)
        assert (
            found["data"]["ce"] == "ZZZ001"
            and found["data"]["statusCode"] == "SOURCE_ACTIVE"
        )
        assert found["data"]["activities"][0]["end"]["value"] is None
        with pytest.raises(Rejected, match="POINTER_CHANGED"):
            state.publish(version, None)
        with pytest.raises(ReadError, match="outside"):
            reader.verify("ZZZ003")
        with pytest.raises(ReadError):
            reader.verify("ZZZ001", mode="history")
        with pytest.raises(ReadError):
            SfcReader(Reader(state.dsn, b"x" * 32), policy).verify("ZZZ001")
        # New failure never changes the accepted pointer or source status.
        failed, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
        a = state.reserve(failed, "ZZZ001", "detail")
        state.settle(a, "missing")
        state.finish(failed)
        assert reader.verify("ZZZ001")["version"] == version
        state.revoke(policy.sha256)
        with pytest.raises(ReadError):
            reader.verify("ZZZ001")
        with pytest.raises(Rejected):
            state.publish(version, version)
    finally:
        with connect(DSN, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE {}").format(sql.Identifier(restored_name))
            )


def test_staging_cannot_exceed_reserved_bytes(model):
    state, policy, _, _ = model
    run, _ = state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
    a = state.reserve(run, "ZZZ001", "detail", max_bytes=1)
    state.settle(a, "ok")
    with pytest.raises(Rejected, match="RESERVED_BYTES_EXCEEDED"):
        state.stage(run, {"ZZZ001": (json.dumps(fake_fact()).encode(), a)})
    with state.connection() as c:
        assert not c.execute("SELECT * FROM curated_sfc.versions").fetchone()


def test_unqualified_tracked_identity_cannot_consume_source_budget(model):
    state, policy, _, _ = model
    with pytest.raises(Rejected, match="COHORT_UNQUALIFIED"):
        state.start(datetime.now(timezone.utc), ["ZZZ999"], policy.sha256)
    with state.connection() as c:
        assert not c.execute("SELECT * FROM curated_sfc.runs").fetchone()
        assert not c.execute("SELECT * FROM curated_sfc.budgets").fetchone()
