"""Host boundaries; source-cycle physical restores are tested separately."""

from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def host():
    path = Path(__file__).resolve().parents[1] / "deploy/curated/sfc-job.py"
    spec = importlib.util.spec_from_file_location("sfc_host_job_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_typed_timer_occurrence_uses_canonical_utc_and_never_human_timespan(host):
    now = datetime(2026, 10, 27, 6, 10, 22, tzinfo=timezone.utc)
    assert host.occurrence("t 10000000", 20000000, now) == (
        "timer",
        "2026-10-27T06:10:00+00:00",
    )
    assert host.occurrence("1h 2min", 20000000, now)[0] == "manual"
    assert host.occurrence("t 0", 20000000, now)[0] == "manual"
    assert host.occurrence("t 1", 100000000, now)[0] == "manual"


def test_collector_child_has_source_env_but_no_admin_uploader_or_docker_socket(
    host, monkeypatch, tmp_path
):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.setattr(host.subprocess, "run", run)
    backend = host.Backend(
        {"image": "mcp-hk-curated:" + "a" * 40, "token": "PRIVATE_UPLOADER_TOKEN"}
    )
    backend.runner("job-state", "--policy-sha256", "b" * 64)
    text = " ".join(commands[0])
    assert "--read-only" in text and "--memory 512m" in text and "--cpus 1" in text
    assert host.ENV in commands[0] and "PRIVATE_UPLOADER_TOKEN" not in text
    assert "docker.sock" not in text and "pg-admin-password" not in text
    artifact = tmp_path / "retrieved.dump"
    artifact.write_bytes(b"proof")
    backend.runner(
        "qualify-restore", restored="sfc_restore_test12345", artifact=artifact
    )
    assert "SFC_RESTORED_DATABASE=sfc_restore_test12345" in commands[1]
    assert any("dst=/proof.dump,readonly" in word for word in commands[1])
    with pytest.raises(host.JobError, match="RESTORE_DATABASE_INVALID"):
        backend.runner("status", restored="curated")


def test_storage_capability_must_match_policy_and_independent_retention_qualification(
    host, monkeypatch
):
    config = {
        "image": "mcp-hk-curated:" + "a" * 40,
        "token": "x" * 40,
        "policySha256": "b" * 64,
        "qualifiedStorageMaximumSeconds": 86400,
    }
    backend = host.Backend(config)
    monkeypatch.setattr(
        backend,
        "request",
        lambda path: io.StringIO(
            json.dumps(
                {
                    "source": "sfc_register",
                    "policySha256": "b" * 64,
                    "configuredRetentionSeconds": 86400,
                }
            )
        ),
    )
    monkeypatch.setattr(
        backend,
        "state",
        lambda: {"backupSeconds": 86400, "oldestVersionExpiresAt": None},
    )
    assert backend.check_storage() == 86400
    monkeypatch.setattr(
        backend,
        "state",
        lambda: {"backupSeconds": 3600, "oldestVersionExpiresAt": None},
    )
    with pytest.raises(host.JobError, match="RETENTION_UNQUALIFIED"):
        backend.check_storage()
    monkeypatch.setattr(
        backend,
        "state",
        lambda: {
            "backupSeconds": 86400,
            "oldestVersionExpiresAt": "2026-01-01T00:00:00+00:00",
        },
    )
    with pytest.raises(host.JobError, match="RETENTION_RECONCILIATION_REQUIRED"):
        backend.check_storage()


def test_wrong_source_receipt_does_not_expose_child_stderr(host, monkeypatch):
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="", stderr="postgresql://secret-password@host"
        ),
    )
    with pytest.raises(host.JobError, match="^SFC_SOURCE_COMMAND_FAILED$"):
        host.Backend({"image": "mcp-hk-curated:" + "a" * 40}).runner("status")


def test_recovery_copy_cannot_reset_the_oldest_source_retention_clock(
    host, monkeypatch
):
    now = datetime(2026, 10, 27, 6, 10, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(host, "datetime", Clock)
    backend = host.Backend(
        {"policySha256": "b" * 64, "qualifiedStorageMaximumSeconds": 86400}
    )
    monkeypatch.setattr(
        backend,
        "request",
        lambda path: io.StringIO(
            json.dumps(
                {
                    "source": "sfc_register",
                    "policySha256": "b" * 64,
                    "configuredRetentionSeconds": 86400,
                }
            )
        ),
    )
    for remaining, expected in [(86399.8, 86399), (3600.2, 3600), (172800, 86400)]:
        monkeypatch.setattr(
            backend,
            "state",
            lambda: {
                "backupSeconds": 86400,
                "oldestVersionExpiresAt": (
                    now + timedelta(seconds=remaining)
                ).isoformat(),
            },
        )
        assert backend.check_storage() == expected
        assert backend.storage_deadline <= now + timedelta(seconds=remaining)
    monkeypatch.setattr(
        backend,
        "state",
        lambda: {
            "backupSeconds": 86400,
            "oldestVersionExpiresAt": now.replace(tzinfo=None).isoformat(),
        },
    )
    with pytest.raises(host.JobError, match="RETENTION_UNQUALIFIED"):
        backend.check_storage()
