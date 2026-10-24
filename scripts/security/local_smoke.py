import hashlib
import json
import urllib.request
import urllib.error
import time
from pathlib import Path

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
root = Path.cwd()
folder = root / ".data/security-local"


def call(path, data=None, method=None, headers=None):
    req = urllib.request.Request(
        "http://localhost:18787" + path, data=data, method=method, headers=headers or {}
    )
    try:
        with opener.open(req, timeout=60) as response:
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(1_000_000)


blob = (folder / "snapshot.tar.gz").read_bytes()
status, body = call(
    "/__ops/snapshot",
    blob,
    "POST",
    {
        "Authorization": "Bearer synthetic-local-operations-only",
        "Content-Length": str(len(blob)),
        "X-Snapshot-SHA256": hashlib.sha256(blob).hexdigest(),
    },
)
print(
    json.dumps(
        {
            "test": "seed-isolated-synthetic-checkpoint",
            "status": status,
            "response": json.loads(body),
        }
    )
)
status, body = call(
    "/__ops/restart",
    b"",
    "POST",
    {
        "Authorization": "Bearer synthetic-local-operations-only",
        "X-Snapshot-SHA256": hashlib.sha256(blob).hexdigest(),
    },
)
print(json.dumps({"test": "restart-local-from-synthetic-checkpoint", "status": status}))
assert status == 200
for path in [
    "/healthz",
    "/api/v1/packs",
    "/api/v1/addresses/search?q=test",
    "/api/v1/plates/search?q=AA88",
    "/api/v1/properties/search?q=test",
]:
    start = time.monotonic()
    status, body = call(path)
    print(
        json.dumps(
            {
                "test": path.split("?")[0],
                "status": status,
                "elapsed": round(time.monotonic() - start, 2),
                "bodyBytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )
    )
