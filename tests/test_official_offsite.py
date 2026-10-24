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
