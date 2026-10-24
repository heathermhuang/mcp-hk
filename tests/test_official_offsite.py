"""Recovery pointer cannot precede all independent object checks."""

import hashlib
import json

import httpx
import pytest

from mcp_open_data_hk.curated.official_offsite import upload, ORIGIN


def test_scoped_uploader_roundtrip_and_failure_never_publish_manifest(tmp_path):
    config = tmp_path / "uploader.json"
    config.write_text(json.dumps({"origin": ORIGIN, "token": "u" * 48}))
    config.chmod(0o600)
    dump = tmp_path / "official.dump"
    dump.write_bytes(b"fixture logical dump")
    source = tmp_path / "source.json"
    source.write_text('{"fixture":true}')
    objects = {}

    def serve(request):
        name = request.url.path.rsplit("/", 1)[-1]
        if request.method == "PUT":
            assert (
                hashlib.sha256(request.content).hexdigest()
                == request.headers["x-object-sha256"]
            )
            if name == "manifest.json":
                assert {"official.dump", "source.json"} <= objects.keys()
            objects[name] = request.content
            return httpx.Response(200)
        return httpx.Response(200, content=objects[name])

    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        receipt = upload(config, dump, source, client)
    assert set(receipt["artifacts"]) == {
        "official.dump",
        "source.json",
        "manifest.json",
    }
    assert not receipt["restoreObserved"]
    objects.clear()

    def corrupt(request):
        if request.method == "PUT":
            objects[request.url.path.rsplit("/", 1)[-1]] = request.content
            return httpx.Response(200)
        return httpx.Response(200, content=b"corrupt")

    with httpx.Client(transport=httpx.MockTransport(corrupt)) as client:
        with pytest.raises(RuntimeError, match="CHECKSUM|SIZE"):
            upload(config, dump, source, client)
    assert "manifest.json" not in objects
    config.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        upload(config, dump, source)


def test_retention_requires_restore_checksum_remote_copy_and_keeps_latest_two(tmp_path):
    import os, time
    from mcp_open_data_hk.curated.official_retention import prune

    config = tmp_path / "uploader.json"
    config.write_text(json.dumps({"origin": ORIGIN, "token": "u" * 48}))
    config.chmod(0o600)
    body = b"qualified dump"
    sha = hashlib.sha256(body).hexdigest()
    now = time.time()
    files = []
    for i in range(1, 5):
        job = f"{i:032x}"
        prefix = f"curated/official/daily/20261024T130000Z-{i:08x}"
        file = tmp_path / ("retrieved-" + job + ".dump")
        file.write_bytes(body)
        os.utime(file, (now - 31 * 86400 - i, now - 31 * 86400 - i))
        files.append(file)
        (tmp_path / ("restore-" + job + ".json")).write_text(
            json.dumps(
                {
                    "freshOffsiteRestoreVerified": True,
                    "backupSha256": sha,
                    "prefix": prefix,
                }
            )
        )
        (tmp_path / ("receipt-" + job + ".json")).write_text(
            json.dumps(
                {
                    "prefix": prefix,
                    "artifacts": {"official.dump": {"sha256": sha, "bytes": len(body)}},
                }
            )
        )
    unknown = tmp_path / ("retrieved-" + "f" * 32 + ".dump")
    unknown.write_bytes(body)
    os.utime(unknown, (0, 0))

    def head(request):
        return httpx.Response(
            200,
            headers={
                "content-length": str(len(body)),
                "x-object-sha256": "0" * 64 if "00000004/" in str(request.url) else sha,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(head)) as client:
        result = prune(tmp_path, config, client, now)
    assert result["expiredLocalDuplicatesPruned"] == 1
    assert (
        files[0].exists()
        and files[1].exists()
        and not files[2].exists()
        and files[3].exists()
    )
    assert unknown.exists() and result["offsiteObjectsDeleted"] == 0
