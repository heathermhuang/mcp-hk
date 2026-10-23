"""Acquisition state and archive trust boundaries, without live source calls."""

import hashlib
import json
import subprocess
import sys

import httpx
import pytest

from mcp_open_data_hk.archive_audit import (
    AuditError,
    SOURCE,
    acquire,
    atomic_json,
    disk_check,
    fingerprint,
    inspect_archive,
    member_records,
    resolve_download,
    safe_workspace,
    validate_download_url,
    validate_members,
)


def source(size):
    return {**SOURCE, "size": size}


def state(workspace):
    return json.loads((workspace / "acquisition.json").read_text())


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_public_form_and_same_host_redirect_are_bounded():
    calls = []

    def serve(request):
        calls.append(str(request.url))
        if request.url.path == "/uc":
            return httpx.Response(
                303,
                headers={"Location": str(request.url).replace("/uc?", "/download?")},
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text=(
                '<form id="download-form" action="https://drive.usercontent.google.com/download">'
                f'<input type="hidden" name="id" value="{SOURCE["fileId"]}">'
                '<input type="hidden" name="export" value="download">'
                '<input type="hidden" name="confirm" value="t"></form>'
            ),
        )

    with client(serve) as c:
        result = resolve_download(c, SOURCE)
    assert "confirm=t" in result
    assert len(calls) == 2


def test_redirect_cannot_send_request_to_another_host():
    calls = []

    def serve(request):
        calls.append(request.url.host)
        return httpx.Response(
            302, headers={"Location": "https://attacker.example/download"}
        )

    with client(serve) as c, pytest.raises(AuditError, match="Unexpected"):
        resolve_download(c, SOURCE)
    assert calls == ["drive.usercontent.google.com"]


@pytest.mark.parametrize(
    "url",
    [
        "http://drive.usercontent.google.com/download?id=" + SOURCE["fileId"],
        "https://drive.usercontent.google.com/download?id=another-file",
        "https://user@drive.usercontent.google.com/download?id=" + SOURCE["fileId"],
    ],
)
def test_download_url_rejects_wrong_source_or_credentials(url):
    with pytest.raises(AuditError):
        validate_download_url(url, SOURCE)


def test_interrupted_download_resumes_exact_range_and_validates_bytes(tmp_path):
    payload = b"x" * (1024 * 1024) + b"last"
    metadata = source(len(payload))

    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield payload[:-4]
            raise httpx.ReadError("interrupted")

    def interrupted(request):
        return httpx.Response(
            200,
            headers={"content-length": str(len(payload)), "etag": '"stable"'},
            stream=Broken(),
        )

    with client(interrupted) as c, pytest.raises(httpx.ReadError):
        acquire(tmp_path, metadata, c, reserve=0)
    assert state(tmp_path)["bytes"] == len(payload) - 4
    assert state(tmp_path)["status"] == "partial"
    calls = []

    def remaining(request):
        if request.headers.get("Range"):
            calls.append(dict(request.headers))
            return httpx.Response(
                206,
                headers={
                    "content-range": f"bytes {len(payload)-4}-{len(payload)-1}/{len(payload)}",
                    "content-length": "4",
                    "etag": '"stable"',
                },
                content=b"last",
            )
        return httpx.Response(
            200, content=b"", headers={"content-type": "application/octet-stream"}
        )

    with client(remaining) as c:
        final = acquire(tmp_path, metadata, c, reserve=0)
    assert final.read_bytes() == payload
    assert calls[0]["if-range"] == '"stable"'
    assert state(tmp_path)["sha256"] == hashlib.sha256(payload).hexdigest()
    assert state(tmp_path)["bytes"] == len(payload)
    assert (
        state(tmp_path)["noticeSha256"]
        == hashlib.sha256((tmp_path / "webb-site-NOTICE.txt").read_bytes()).hexdigest()
    )
    assert "failed" in (tmp_path / "receipts.jsonl").read_text()


def checkpoint(workspace, metadata, payload):
    (workspace / "archive.7z.part").write_bytes(payload)
    atomic_json(
        workspace / "acquisition.json",
        {
            "sourceFingerprint": fingerprint(metadata),
            "bytes": len(payload),
            "partialSha256": hashlib.sha256(payload).hexdigest(),
            "status": "partial",
        },
    )


def test_source_or_partial_change_is_not_resumed(tmp_path):
    metadata = source(6)
    checkpoint(tmp_path, metadata, b"abc")
    with client(lambda r: pytest.fail("must not contact source")) as c:
        with pytest.raises(AuditError, match="Metadata differs"):
            acquire(tmp_path, {**metadata, "modifiedTime": "changed"}, c, reserve=0)
        (tmp_path / "archive.7z.part").write_bytes(b"bad")
        with pytest.raises(AuditError, match="Partial bytes"):
            acquire(tmp_path, metadata, c, reserve=0)
    assert not (tmp_path / "archive.7z").exists()


def test_resume_refuses_full_response_instead_of_appending(tmp_path):
    metadata = source(6)
    checkpoint(tmp_path, metadata, b"abc")
    with client(lambda r: httpx.Response(200, content=b"abcdef")) as c:
        with pytest.raises(AuditError, match="exact remaining byte range"):
            acquire(tmp_path, metadata, c, reserve=0)
    assert (tmp_path / "archive.7z.part").read_bytes() == b"abc"


def test_uncommitted_tail_is_not_trusted_after_process_loss(tmp_path):
    metadata = source(6)
    checkpoint(tmp_path, metadata, b"abc")
    with (tmp_path / "archive.7z.part").open("ab") as f:
        f.write(b"uncommitted")

    def serve(request):
        if request.headers.get("range"):
            return httpx.Response(
                206, content=b"def", headers={"content-range": "bytes 3-5/6"}
            )
        return httpx.Response(200)

    with client(serve) as c:
        assert acquire(tmp_path, metadata, c, reserve=0).read_bytes() == b"abcdef"
    assert "discardedUncommittedBytes" in (tmp_path / "receipts.jsonl").read_text()


def test_final_rename_crash_can_be_verified_without_redownload(tmp_path):
    metadata = source(3)
    checkpoint(tmp_path, metadata, b"abc")
    (tmp_path / "archive.7z.part").replace(tmp_path / "archive.7z")
    with client(lambda r: pytest.fail("must not redownload")) as c:
        assert acquire(tmp_path, metadata, c, reserve=0).read_bytes() == b"abc"
    assert state(tmp_path)["status"] == "verified"


@pytest.mark.parametrize(
    "payload,size,code",
    [(b"too long", 3, "DOWNLOAD_LIMIT"), (b"short", 10, "INCOMPLETE_DOWNLOAD")],
)
def test_response_size_is_enforced_without_content_length(
    tmp_path, payload, size, code
):
    with client(lambda r: httpx.Response(200, stream=httpx.ByteStream(payload))) as c:
        with pytest.raises(AuditError) as error:
            acquire(tmp_path, source(size), c, reserve=0)
    assert error.value.code == code
    assert not (tmp_path / "archive.7z").exists()


def test_disk_reserve_checked_before_network(tmp_path, monkeypatch):
    class Disk:
        free = 10

    monkeypatch.setattr(
        "mcp_open_data_hk.archive_audit.shutil.disk_usage", lambda p: Disk()
    )
    with pytest.raises(AuditError, match="free-space reserve"):
        disk_check(tmp_path, needed=5, reserve=6)


@pytest.mark.parametrize(
    "name,extra",
    [
        ("../table.sql", {}),
        ("/tmp/table.sql", {}),
        ("C:/table.sql", {}),
        ("folder\\table.sql", {}),
        ("a//b.sql", {}),
        ("safe.sql", {"Symbolic Link": "elsewhere"}),
        ("safe.sql", {"Attributes": "A_ lrwxrwxrwx"}),
        ("safe.sql", {"Hard Link": "elsewhere"}),
        ("run.sh", {}),
    ],
)
def test_archive_paths_and_non_data_members_are_rejected(name, extra):
    with pytest.raises(AuditError):
        validate_members([{"Path": name, "Size": "4", **extra}])


def test_member_budget_and_case_aliases_are_rejected():
    with pytest.raises(AuditError, match="expansion"):
        validate_members([{"Path": "a.sql", "Size": "12"}], max_expanded=10)
    with pytest.raises(AuditError, match="Unsafe"):
        validate_members([{"Path": "a.sql"}, {"Path": "A.sql"}])
    result = validate_members(
        member_records("Path = enigma/a.sql\nSize = 9\nAttributes = A_ -rw-r--r--\n\n")
    )
    assert result["declaredExpandedBytes"] == 9


def test_workspace_does_not_follow_symlinks(tmp_path):
    (tmp_path / "linked").symlink_to(tmp_path / "other")
    with pytest.raises(AuditError):
        safe_workspace(tmp_path / "linked")


def test_archive_listing_is_stopped_before_unbounded_capture(tmp_path, monkeypatch):
    archive = tmp_path / "archive.7z"
    archive.write_bytes(b"fixture")
    atomic_json(
        tmp_path / "acquisition.json",
        {"status": "verified", "sha256": hashlib.sha256(b"fixture").hexdigest()},
    )
    native = subprocess.Popen

    def oversized(*args, **kwargs):
        return native(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.buffer.write(b'x' * (2 * 1024 * 1024 + 1))",
            ],
            **kwargs,
        )

    monkeypatch.setattr("mcp_open_data_hk.archive_audit.subprocess.Popen", oversized)
    with pytest.raises(AuditError, match="2 MiB"):
        inspect_archive(tmp_path)
    assert not (tmp_path / "archive-members.json").exists()
