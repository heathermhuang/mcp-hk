"""Source-job outcome proofs, real physical restores, and zero upstream calls."""

from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
import uuid

import httpx
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from test_sfc_postgres import model as base_model, stage, DSN, pytestmark as base_marks
from test_sfc import fake_policy
from mcp_open_data_hk.curated.backup import backup, restore
from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.sfc.contracts import Rejected
from mcp_open_data_hk.curated.sfc.job import run_cycle
from mcp_open_data_hk.curated.sfc.public_register import Collector, ROUTE
from mcp_open_data_hk.curated.sfc.state import State

model = base_model
pytestmark = base_marks
GATE = {"qualified": True, "officialVersion": "official-" + "a" * 32}


class CollectedFixture:
    def __init__(self, state, policy):
        self.state, self.policy, self.calls = state, policy, 0

    def collect(self, when, cohort, provenance, source_release):
        self.calls += 1
        version, _, run = stage(self.state, self.policy, tuple(cohort), scheduled=when)
        return {"state": "validated", "version": version, "runId": run}


def recovery(state, tmp_path, fail=None):
    @contextmanager
    def recovered(version, kind):
        if fail == kind:
            raise Rejected("SFC_OFFSITE_RETRIEVAL_FAILED")
        config = conninfo_to_dict(state.dsn)
        name = "sfc_job_restore_" + uuid.uuid4().hex[:10]
        artifact = tmp_path / (kind + "-" + uuid.uuid4().hex + ".dump")
        receipt = backup(
            os.environ["CURATED_TEST_CONTAINER"], config["dbname"], version, artifact
        )
        with connect(DSN, autocommit=True) as c:
            c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            restore(
                os.environ["CURATED_TEST_CONTAINER"], name, artifact, receipt["sha256"]
            )
            yield State(make_conninfo(**dict(config, dbname=name))), artifact, receipt[
                "sha256"
            ]
        finally:
            with connect(DSN, autocommit=True) as c:
                c.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))

    return recovered


def test_cycle_requires_both_actual_restores_and_preserves_independent_outcomes(
    model, tmp_path
):
    state, policy, reader, _ = model
    collector = CollectedFixture(state, policy)
    result = run_cycle(
        state,
        policy.sha256,
        datetime.now(timezone.utc),
        ["ZZZ001"],
        recovery(state, tmp_path),
        collector=collector,
        check_recovery=lambda: GATE,
    )
    assert result["state"] == "accepted_and_recovery_verified" and collector.calls == 1
    assert result["candidateProof"]["acceptedPointerIncluded"] is False
    assert result["acceptedProof"]["acceptedPointerIncluded"] is True
    assert result["publicModesGranted"] is False
    status = reader.status()
    outcomes = status["lastRun"]["job_outcomes"]
    assert all(
        outcomes[k]["state"] == "succeeded"
        for k in ("collection", "backup", "publication", "accepted_backup")
    )
    assert (
        status["lastRun"]["provenance"] == "manual"
        and status["unresolvedRequests"] == 0
    )


def test_failed_candidate_backup_resumes_without_repeating_collection(model, tmp_path):
    state, policy, _, _ = model
    collector = CollectedFixture(state, policy)
    when = datetime.now(timezone.utc)
    with pytest.raises(Rejected, match="OFFSITE_RETRIEVAL_FAILED"):
        run_cycle(
            state,
            policy.sha256,
            when,
            ["ZZZ001"],
            recovery(state, tmp_path, fail="candidate"),
            collector=collector,
            check_recovery=lambda: GATE,
        )
    with state.connection() as c:
        row = c.execute("SELECT state,job_outcomes FROM curated_sfc.runs").fetchone()
        assert (
            row["state"] == "validated"
            and row["job_outcomes"]["collection"]["state"] == "succeeded"
        )
        assert row["job_outcomes"]["backup"]["state"] == "failed"
        assert not c.execute("SELECT * FROM curated_sfc.pointer").fetchone()
    result = run_cycle(
        state,
        policy.sha256,
        when,
        ["ZZZ001"],
        recovery(state, tmp_path),
        collector=collector,
        check_recovery=lambda: pytest.fail(
            "A retained candidate must not require new growth admission"
        ),
    )
    assert result["resumedCandidateWithoutSourceRead"] and collector.calls == 1


def test_failed_accepted_backup_repairs_only_recovery_without_new_source_read(
    model, tmp_path
):
    state, policy, _, _ = model
    collector = CollectedFixture(state, policy)
    when = datetime.now(timezone.utc)
    with pytest.raises(Rejected, match="OFFSITE_RETRIEVAL_FAILED"):
        run_cycle(
            state,
            policy.sha256,
            when,
            ["ZZZ001"],
            recovery(state, tmp_path, fail="accepted"),
            collector=collector,
            check_recovery=lambda: GATE,
        )
    result = run_cycle(
        state,
        policy.sha256,
        when,
        ["ZZZ001"],
        recovery(state, tmp_path),
        collector=collector,
        check_recovery=lambda: pytest.fail(
            "Recovery repair must not request new collection"
        ),
    )
    assert (
        result["state"] == "accepted_recovery_verified"
        and result["sourceReads"] == 0
        and collector.calls == 1
    )


def test_success_flags_cannot_substitute_for_restore_or_accepted_pointer(
    model, tmp_path
):
    state, policy, _, _ = model
    version, _, run = stage(state, policy)
    with pytest.raises(Rejected, match="RESTORE_REQUIRED"):
        state.job_outcome(run, "backup", "succeeded", artifact_sha256="a" * 64)
    with recovery(state, tmp_path)(version, "candidate") as (target, artifact, sha):
        state.qualify_restore(version, target, artifact, sha)
    state.publish(version, None)
    with pytest.raises(Rejected, match="ACCEPTED_RECOVERY_REQUIRED"):
        state.job_outcome(run, "accepted_backup", "succeeded", artifact_sha256=sha)


def test_unqualified_recovery_gate_cannot_start_collection(model, tmp_path):
    state, policy, _, _ = model
    collector = CollectedFixture(state, policy)
    with pytest.raises(Rejected, match="RECOVERY_GATE_UNQUALIFIED"):
        run_cycle(
            state,
            policy.sha256,
            datetime.now(timezone.utc),
            ["ZZZ001"],
            recovery(state, tmp_path),
            collector=collector,
            check_recovery=lambda: {"qualified": False},
            provenance="timer",
            source_release="f" * 40,
        )
    assert collector.calls == 0


def test_timer_provenance_is_distinct_and_cannot_relabel_an_existing_manual_run(model):
    state, policy, reader, _ = model
    when = datetime.now(timezone.utc)
    state.start(when, ["ZZZ001"], policy.sha256)
    with pytest.raises(Rejected, match="OCCURRENCE_CONFLICT"):
        state.start(when, ["ZZZ001"], policy.sha256, "timer", "f" * 40)
    assert reader.status()["lastRun"]["provenance"] == "manual"
    with pytest.raises(Rejected, match="PROVENANCE_INVALID"):
        state.start(when + timedelta(seconds=1), ["ZZZ001"], policy.sha256, "timer")


def test_transport_uncertainty_stays_charged_and_blocks_the_next_occurrence(model):
    state, _, _, _ = model
    policy = fake_policy(route=ROUTE)
    state.activate(policy, policy.sha256)
    calls = []

    def timeout(request):
        calls.append(str(request.url))
        raise httpx.ReadTimeout("unknown response")

    with pytest.raises(Rejected, match="SOURCE_UNAVAILABLE"):
        Collector(state, policy, transport=httpx.MockTransport(timeout)).collect(
            datetime.now(timezone.utc), ["ZZZ001"]
        )
    with state.connection() as c:
        assert (
            c.execute("SELECT state FROM curated_sfc.attempts").fetchone()["state"]
            == "unknown"
        )
        assert (
            c.execute("SELECT requests FROM curated_sfc.budgets").fetchone()["requests"]
            == 1
        )
    with pytest.raises(Rejected, match="RECONCILIATION_REQUIRED"):
        state.start(datetime.now(timezone.utc), ["ZZZ001"], policy.sha256)
    assert len(calls) == 1


def test_retained_candidate_cannot_automatically_regress_a_newer_accepted_pointer(
    model, tmp_path
):
    state, policy, _, _ = model
    older, _, _ = stage(state, policy)
    newer, _, run = stage(state, policy, scheduled=datetime.now(timezone.utc))
    with recovery(state, tmp_path)(newer, "candidate") as (target, artifact, sha):
        state.qualify_restore(newer, target, artifact, sha)
    state.publish(newer, None)
    with recovery(state, tmp_path)(newer, "accepted") as (target, artifact, sha):
        state.qualify_restore(newer, target, artifact, sha)
    state.job_outcome(run, "accepted_backup", "succeeded", artifact_sha256=sha)
    with pytest.raises(Rejected, match="CANDIDATE_BASE_CHANGED"):
        run_cycle(
            state,
            policy.sha256,
            datetime.now(timezone.utc),
            ["ZZZ001"],
            recovery(state, tmp_path),
            collector=CollectedFixture(state, policy),
        )
    assert state.job_state(policy.sha256)["acceptedVersion"] == newer
    assert state.job_state(policy.sha256)["pendingCandidate"]["version"] == older


def test_prebuilt_export_uses_restored_accepted_state_and_fresh_policy(
    model, tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient
    from sfc_support import source_page
    from mcp_open_data_hk.curated.backend import create_app
    from mcp_open_data_hk.curated.sfc.artifacts import build_from_reader
    from mcp_open_data_hk.curated.sfc import read
    from mcp_open_data_hk.curated.read import ReadError

    state, base, reader, _ = model
    policy = fake_policy(route=ROUTE, modes=dict(base.modes, export="allowed"))
    state.activate(policy, policy.sha256)
    reader.policy = policy
    result = run_cycle(
        state,
        policy.sha256,
        datetime.now(timezone.utc),
        ["ZZZ001"],
        recovery(state, tmp_path),
        collector=Collector(
            state,
            policy,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=source_page(), headers={"Content-Type": "text/html"}
                )
            ),
        ),
        check_recovery=lambda: GATE,
    )
    version = result["version"]
    target = tmp_path / "artifacts"
    proof = build_from_reader(reader, version, target)
    monkeypatch.setattr(read, "configured_policy", lambda: policy)
    monkeypatch.setenv("MCP_HK_SFC_EXPORT_DIRECTORY", str(target))
    app = create_app(reader.reader, "b" * 40)
    with TestClient(app) as client:
        assert client.get("/v1/sfc/exports/" + version).status_code == 401
        response = client.get(
            "/v1/sfc/exports/" + version,
            headers={"Authorization": "Bearer " + "b" * 40},
        )
        assert (
            response.status_code == 200
            and response.headers["x-content-sha256"] == proof["sha256"]
        )
        assert (
            response.headers["x-sfc-version"] == version
            and response.content[:2] == b"PK"
        )
        state.revoke(policy.sha256)
        assert (
            client.get(
                "/v1/sfc/exports/" + version,
                headers={"Authorization": "Bearer " + "b" * 40},
            ).status_code
            == 503
        )
    with pytest.raises(ReadError):
        reader.artifact_state(version)
