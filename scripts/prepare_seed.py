"""Create and restore-test the real local dataset before its first deployment."""

import json
import tempfile
from pathlib import Path

from mcp_open_data_hk.operations import checkpoint, restore
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

store = Store(".data/mcp-hk.sqlite3")
path, digest = checkpoint(store.path)
with tempfile.TemporaryDirectory() as directory:
    target = str(Path(directory) / "mcp-hk.sqlite3")
    restore(path.read_bytes(), digest, target)
    status = Service(Store(target)).status()
    if not status["ready"]:
        raise SystemExit("Restored database is not ready")
receipt = {
    "file": str(path),
    "sha256": digest,
    "bytes": path.stat().st_size,
    "restoredSources": [
        {"sourceId": s["sourceId"], "recordCount": s.get("recordCount")}
        for s in status["sources"]
    ],
}
Path(".data/seed-receipt.json").write_text(json.dumps(receipt, indent=2))
print(json.dumps(receipt))
