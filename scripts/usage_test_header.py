"""Mint a short-lived MCP.HK operator-test header without exposing the ops token."""

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--secrets",
        type=Path,
        default=Path("deploy/cloudflare/.ops-secrets.json"),
    )
    secret = json.loads(parser.parse_args().secrets.read_text())["OPS_TOKEN"]
    issued = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), f"mcp.hk:usage-test:v1:{issued}".encode(), hashlib.sha256
    ).hexdigest()
    print(f"X-Mcp-Usage-Test: {issued}.{signature}")


if __name__ == "__main__":
    main()
