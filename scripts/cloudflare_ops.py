"""Operator-only authenticated deployment/backup checks. Never prints credentials."""

import argparse
import json
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from mcp_open_data_hk.operations import MAX_BACKUP, restore
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Operator requests may not redirect")


parser = argparse.ArgumentParser()
parser.add_argument(
    "action",
    choices=[
        "seed",
        "status",
        "backup",
        "restaurants",
        "population",
        "all",
        "catalogue",
        "resources",
        "restore-test",
        "restart",
        "publish-overview",
        "usage",
    ],
)
parser.add_argument("--origin", default="https://mcp-hk.measurable.workers.dev")
parser.add_argument("--days", type=int, default=7, choices=range(1, 91))
args = parser.parse_args()
if urlsplit(args.origin).scheme != "https" or urlsplit(args.origin).hostname not in {
    "mcp.hk",
    "mcp-hk.measurable.workers.dev",
}:
    raise SystemExit("Unrecognized deployment origin")
secret = json.loads(Path("deploy/cloudflare/.ops-secrets.json").read_text())[
    "OPS_TOKEN"
]
headers = {"Authorization": "Bearer " + secret, "User-Agent": "mcp.hk-operations/0.3"}
method, data = "GET", None
if args.action == "seed":
    seed = json.loads(Path(".data/seed-receipt.json").read_text())
    data = Path(seed["file"]).read_bytes()
    headers["X-Snapshot-SHA256"] = seed["sha256"]
    if len(data) > MAX_BACKUP:
        raise SystemExit("Seed exceeds upload limit")
    path, method = "/__ops/snapshot", "POST"
elif args.action == "publish-overview":
    path, method = "/__ops/publish-overview", "POST"
elif args.action == "restart":
    status_request = urllib.request.Request(
        args.origin + "/api/v1/operations",
        headers={"User-Agent": "mcp.hk-operations/0.4"},
    )
    with urllib.request.build_opener(NoRedirect).open(
        status_request, timeout=30
    ) as response:
        manifest = json.loads(response.read(10000))
    headers["X-Snapshot-SHA256"] = manifest["backup"]["sha256"]
    path, method = "/__ops/restart", "POST"
elif args.action == "restore-test":
    path = "/__ops/snapshot"
elif args.action == "usage":
    path = "/__ops/usage?days=" + str(args.days)
elif args.action == "status":
    path = "/__ops/status"
else:
    path, method = "/__ops/run?pack=" + args.action, "POST"
request = urllib.request.Request(
    args.origin + path, data=data, method=method, headers=headers
)
try:
    with urllib.request.build_opener(NoRedirect).open(request, timeout=600) as response:
        if args.action == "restore-test":
            packed = response.read(MAX_BACKUP + 1)
            with tempfile.TemporaryDirectory() as directory:
                target = str(Path(directory) / "restored.sqlite3")
                restore(packed, response.headers.get("X-Snapshot-SHA256", ""), target)
                state = Service(Store(target)).status()
                print(
                    json.dumps(
                        {
                            "restored": state["ready"],
                            "sources": [
                                {
                                    "sourceId": s["sourceId"],
                                    "recordCount": s.get("recordCount"),
                                }
                                for s in state["sources"]
                            ],
                        }
                    )
                )
        else:
            print(
                response.read(2_000_000 if args.action == "usage" else 10000).decode()
            )
except urllib.error.HTTPError as exc:
    code = ""
    try:
        payload = json.loads(exc.read(10000))
        value = payload.get("error", {}).get("code", "")
        if isinstance(value, str) and re.fullmatch(r"[A-Z0-9_]{1,80}", value):
            code = " (" + value + ")"
    except (ValueError, AttributeError, TypeError):
        pass
    retry = exc.headers.get("Retry-After", "")
    retry_note = "; retry after " + retry + " seconds" if re.fullmatch(r"[0-9]{1,6}", retry) else ""
    raise SystemExit("Operator endpoint returned HTTP " + str(exc.code) + code + retry_note) from None
