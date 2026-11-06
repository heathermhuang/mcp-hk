import hashlib
import io
import json
import tarfile
import time
from contextlib import contextmanager

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


@pytest.mark.parametrize("compression", [1, 6])
def test_checkpoint_restore_recovers_database_and_captures(
    operational, tmp_path, compression
):
    path, digest = checkpoint(operational.path, compresslevel=compression)
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


def test_fast_checkpoint_recompresses_same_snapshot_before_transfer_limit(
    operational, tmp_path, monkeypatch
):
    from mcp_open_data_hk import operations

    captures = tmp_path / "source" / "captures"
    data = json.dumps({"source": "public fixture " * 100000}).encode()
    (captures / (hashlib.sha256(data).hexdigest() + ".json")).write_bytes(data)
    original_names = {p.name for p in captures.glob("*.json")}
    fast, _ = checkpoint(operational.path, compresslevel=1)
    strong, _ = checkpoint(operational.path, compresslevel=6)
    limit = (fast.stat().st_size + strong.stat().st_size) // 2
    assert strong.stat().st_size < limit < fast.stat().st_size
    monkeypatch.setattr(operations, "FAST_COMPRESSION_TARGET", limit)
    monkeypatch.setattr(operations, "MAX_BACKUP", limit)
    original_open = tarfile.open
    levels = []

    @contextmanager
    def concurrent_write(*args, **kwargs):
        with original_open(*args, **kwargs) as archive:
            yield archive
        if kwargs.get("mode") == "w:gz" or (len(args) > 1 and args[1] == "w:gz"):
            levels.append(kwargs["compresslevel"])
            if len(levels) == 1:
                operational.publish(
                    "restaurants",
                    [{"id": "later-live-write", "latitude": 22.4, "longitude": 114.2}],
                    operational.active("restaurants"),
                )
                later = b'{"later":"capture"}'
                (captures / (hashlib.sha256(later).hexdigest() + ".json")).write_bytes(
                    later
                )

    monkeypatch.setattr(operations.tarfile, "open", concurrent_write)
    packed, digest = checkpoint(operational.path, compresslevel=1)
    assert levels == [1, 6]
    assert packed.stat().st_size <= limit
    target = tmp_path / "adaptive-restored" / "app.sqlite3"
    restore(packed.read_bytes(), digest, str(target))
    assert Store(str(target)).snapshot("restaurants")[1][0]["id"] == "test-licence"
    assert {
        p.name for p in (target.parent / "captures").glob("*.json")
    } == original_names
    assert operational.snapshot("restaurants")[1][0]["id"] == "later-live-write"


def test_recompression_cannot_bypass_transfer_limit_or_remove_accepted_archive(
    operational, monkeypatch
):
    from mcp_open_data_hk import operations

    accepted, digest = checkpoint(operational.path)
    active = operational.active("restaurants")
    monkeypatch.setattr(operations, "MAX_BACKUP", 1)
    with pytest.raises(ValueError, match="storage transfer limit"):
        checkpoint(operational.path, compresslevel=1)
    assert accepted.exists()
    assert hashlib.sha256(accepted.read_bytes()).hexdigest() == digest
    assert operational.active("restaurants") == active


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


@pytest.mark.parametrize("legacy_text", [False, True])
def test_transport_checkpoint_preserves_metadata_and_record_cache(
    operational, tmp_path, legacy_text
):
    from mcp_open_data_hk.catalogue_store import CatalogueStore

    catalogue = CatalogueStore(operational)
    dataset = {"id": "sample", "provider": "Example", "catalogue": "DATA.GOV.HK"}
    resource = {
        "id": "r1",
        "datasetId": "sample",
        "format": "CSV",
        "url": "https://example.gov.hk/data.csv",
    }
    catalogue.publish([dataset], [resource], {})
    schema = {"fields": [{"name": "id", "types": ["string"]}], "format": "CSV"}
    catalogue.accept("r1", "variant", [{"id": "001"}], schema, "a" * 64, {})
    with operational.connect() as db:
        assert (
            db.execute("SELECT typeof(payload) FROM inventory_resources").fetchone()[0]
            == "blob"
        )
        if legacy_text:
            import zlib

            for table, column in [
                ("inventory_resources", "payload"),
                ("resource_variants", "schema_json"),
            ]:
                for rowid, payload in db.execute(
                    f"SELECT rowid,{column} FROM {table}"
                ).fetchall():
                    db.execute(
                        f"UPDATE {table} SET {column}=? WHERE rowid=?",
                        (zlib.decompress(payload).decode(), rowid),
                    )
    path, digest = checkpoint(operational.path)
    target = tmp_path / "transport-restored" / "app.sqlite3"
    restore(path.read_bytes(), digest, str(target))
    recovered = CatalogueStore(Store(str(target)))
    assert recovered.resource("r1") == resource
    assert recovered.cached("variant")["value"]["rows"] == [{"id": "001"}]
    assert recovered.coverage()["resources"]["byStatus"] == {"queryable": 1}
    with recovered.store.connect() as db:
        assert (
            db.execute("SELECT typeof(payload) FROM inventory_resources").fetchone()[0]
            == "text"
        )
        assert (
            db.execute("SELECT typeof(schema_json) FROM resource_variants").fetchone()[
                0
            ]
            == "blob"
        )
        assert (
            db.execute("SELECT typeof(payload) FROM resource_cache").fetchone()[0]
            == "blob"
        )
    with operational.connect() as db:
        assert db.execute("SELECT typeof(payload) FROM inventory_resources").fetchone()[
            0
        ] == ("text" if legacy_text else "blob")
