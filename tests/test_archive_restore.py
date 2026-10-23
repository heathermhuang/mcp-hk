import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from mcp_open_data_hk.archive_audit import AuditError, GIB
from mcp_open_data_hk.archive_restore import IMAGE, isolation, member_file
from mcp_open_data_hk.archive_extract import extract_member


def config(workspace):
    return {
        "Id": "task-owned",
        "Config": {"Image": IMAGE},
        "HostConfig": {
            "NetworkMode": "none",
            "Memory": 6 * GIB,
            "Privileged": False,
            "PortBindings": {},
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(workspace / "mysql"),
                "Destination": "/var/lib/mysql",
            }
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        {"NetworkMode": "bridge"},
        {"Memory": 0},
        {"Memory": 9 * GIB},
        {"Privileged": True},
        {"PortBindings": {"3306/tcp": [{"HostPort": "3306"}]}},
    ],
)
def test_restore_rejects_networked_unbounded_or_privileged_database(
    tmp_path, monkeypatch, change
):
    c = config(tmp_path)
    c["HostConfig"].update(change)
    monkeypatch.setattr(
        "mcp_open_data_hk.archive_restore.docker",
        lambda *a: SimpleNamespace(stdout=json.dumps([c]).encode()),
    )
    with pytest.raises(AuditError):
        isolation(tmp_path, "candidate")


def test_restore_rejects_unrelated_image_or_host_mount(tmp_path, monkeypatch):
    base = config(tmp_path)
    for candidate in [
        {**base, "Config": {"Image": "another-image"}},
        {
            **base,
            "Mounts": base["Mounts"]
            + [{"Type": "bind", "Source": "/unrelated", "Destination": "/host"}],
        },
    ]:
        monkeypatch.setattr(
            "mcp_open_data_hk.archive_restore.docker",
            lambda *a: SimpleNamespace(stdout=json.dumps([candidate]).encode()),
        )
        with pytest.raises(AuditError):
            isolation(tmp_path, "candidate")
    monkeypatch.setattr(
        "mcp_open_data_hk.archive_restore.docker",
        lambda *a: SimpleNamespace(stdout=json.dumps([copy.deepcopy(base)]).encode()),
    )
    assert isolation(tmp_path, "candidate")["network"] == "none"


def test_member_receipt_cannot_redirect_restore_to_a_host_file(tmp_path):
    (tmp_path / "acquisition.json").write_text(
        json.dumps({"status": "verified", "sha256": "source"})
    )
    (tmp_path / "archive-members.json").write_text(
        json.dumps({"members": [{"path": "enigmaData.sql", "bytes": 1}]})
    )
    (tmp_path / "member-proof.json").write_text(
        json.dumps(
            {
                "member": "enigmaData.sql",
                "path": "../../host-file",
                "archiveSha256": "source",
                "bytes": 1,
            }
        )
    )
    with pytest.raises(AuditError, match="accepted source inventory"):
        member_file(tmp_path, "Data")


def test_archive_member_is_not_parsed_as_a_native_option(tmp_path, monkeypatch):
    (tmp_path / "archive.7z").write_bytes(b"fixture")
    (tmp_path / "archive-members.json").write_text(
        json.dumps(
            {
                "archiveSha256": hashlib.sha256(b"fixture").hexdigest(),
                "members": [{"path": "-ooutside.sql", "bytes": 1, "directory": False}],
            }
        )
    )

    def launch(command, **kwargs):
        assert command[-2:] == ["--", "-ooutside.sql"]
        raise OSError("fixture; no process launched")

    monkeypatch.setattr("mcp_open_data_hk.archive_extract.subprocess.Popen", launch)
    with pytest.raises(OSError, match="fixture"):
        extract_member(tmp_path, "-ooutside.sql", reserve=0)


def test_stalled_database_pipe_cannot_bypass_import_deadline():
    import subprocess
    import sys
    import time
    from mcp_open_data_hk.archive_restore import DeadlineWriter

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"], stdin=subprocess.PIPE
    )
    started = time.monotonic()
    try:
        with DeadlineWriter(child.stdin, started + 0.1) as sink:
            with pytest.raises(AuditError) as error:
                sink.write(b"x" * (1024 * 1024))
        assert error.value.code == "RESTORE_TIMEOUT"
        assert time.monotonic() - started < 1
    finally:
        child.kill()
        child.wait(timeout=5)
        child.stdin.close()


def test_loader_grants_must_be_exactly_current_schema():
    from mcp_open_data_hk.archive_restore import validate_loader_grants

    readonly = [
        "GRANT USAGE ON *.* TO `audit_loader`@`localhost`",
        "GRANT SELECT ON `audit\\_new`.* TO `audit_loader`@`localhost`",
    ]
    assert validate_loader_grants("audit_new", readonly) == readonly
    for extra in [
        "GRANT SELECT, INSERT ON `audit\\_old`.* TO `audit_loader`@`localhost`",
        "GRANT FILE ON *.* TO `audit_loader`@`localhost`",
    ]:
        with pytest.raises(AuditError):
            validate_loader_grants("audit_new", readonly + [extra])
