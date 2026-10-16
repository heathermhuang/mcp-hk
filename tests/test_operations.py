import hashlib
import io
import json
import tarfile
import time

import pytest
from fastapi.testclient import TestClient

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.operations import checkpoint, restore
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.sources import DISTRICTS
from mcp_open_data_hk.storage import Store


@pytest.fixture
def operational(tmp_path):
    store = Store(str(tmp_path / "source" / "app.sqlite3"))
    store.publish(
        "restaurants",
        [{"id": "test-licence", "latitude": 22.3, "longitude": 114.1}],
        None,
    )
    store.publish(
        "population",
        [{"id": d["id"] + ":2024", "districtId": d["id"]} for d in DISTRICTS],
        None,
    )
    captures = tmp_path / "source" / "captures"
    captures.mkdir()
    data = json.dumps({"test": "public-source-fixture"}).encode()
    (captures / (hashlib.sha256(data).hexdigest() + ".json")).write_bytes(data)
    return store


def test_checkpoint_restore_recovers_database_and_captures(operational, tmp_path):
    path, digest = checkpoint(operational.path)
    target = tmp_path / "restored" / "app.sqlite3"
    restore(path.read_bytes(), digest, str(target))
    assert Service(Store(str(target))).status()["ready"]
    assert len(list((target.parent / "captures").glob("*.json"))) == 1
    assert Store(str(target)).snapshot("restaurants")[1][0]["id"] == "test-licence"


def test_corrupt_backup_preserves_existing_database(operational):
    before = operational.active("restaurants")
    path, _ = checkpoint(operational.path)
    with pytest.raises(ValueError, match="checksum"):
        restore(path.read_bytes(), "0" * 64, operational.path)
    assert operational.active("restaurants") == before


def test_archive_path_traversal_is_rejected(tmp_path):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        archive.addfile(info, io.BytesIO(b"x"))
    data = output.getvalue()
    with pytest.raises(ValueError, match="unexpected path"):
        restore(data, hashlib.sha256(data).hexdigest(), str(tmp_path / "db.sqlite3"))
    assert not (tmp_path.parent / "escape").exists()


def test_private_operations_fail_closed_without_token(operational, monkeypatch):
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", "test-token-only")
    with TestClient(create_app(Service(operational))) as client:
        assert client.post("/__ops/backup").status_code == 404
        response = client.post(
            "/__ops/backup", headers={"Authorization": "Bearer test-token-only"}
        )
        assert response.status_code == 200
        assert (
            response.headers["x-snapshot-sha256"]
            == hashlib.sha256(response.content).hexdigest()
        )
        assert (
            client.post(
                "/__ops/refresh?pack=unknown",
                headers={"Authorization": "Bearer test-token-only"},
            ).status_code
            == 400
        )


def test_edge_mode_requires_signed_forwarding(operational, monkeypatch):
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", "test-token-only")
    monkeypatch.setenv("MCP_HK_EDGE_MODE", "true")
    with TestClient(create_app(Service(operational))) as client:
        assert client.get("/healthz").status_code == 403
        assert (
            client.get(
                "/healthz", headers={"x-mcp-edge-token": "test-token-only"}
            ).status_code
            == 200
        )


def test_pruning_keeps_recently_retired_generations(operational):
    original = operational.active("restaurants")
    with operational.connect() as db:
        db.execute(
            "UPDATE snapshots SET retrieved=? WHERE id=?",
            (time.time() - 10 * 86400, original),
        )
    second = operational.publish("restaurants", [{"id": "second"}], original)
    operational.publish("restaurants", [{"id": "third"}], second)
    operational.prune()
    assert operational.snapshot("restaurants", original)[0]["id"] == original
    with operational.connect() as db:
        db.execute(
            "UPDATE snapshots SET retired=? WHERE id=?",
            (time.time() - 3 * 86400, original),
        )
    operational.prune()
    with pytest.raises(Exception, match="SNAPSHOT_EXPIRED"):
        operational.snapshot("restaurants", original)
