"""Resumable REST/MCP proof for the existing full-cohort company owner.

Requires a fresh SELECT-only official_acceptance cohort; staged state fails before
network. Browser and real download cells remain separate, never inferred from API.
"""

import argparse
import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from .acceptance import Journal, company_plan, verify_company_record, sha, canonical


class PublicVerifier:
    def __init__(self, folder, transport=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.client = httpx.Client(
            timeout=30, trust_env=False, follow_redirects=False, transport=transport
        )
        self.last = 0
        self.headers = {
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        }
        self.initialized = False
        self.sequence = 0

    def request(self, method, path, **kwargs):
        time.sleep(max(0, 2.1 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        body = bytearray()
        with self.client.stream(method, "https://mcp.hk" + path, **kwargs) as response:
            if response.status_code not in {200, 202}:
                # In particular, no automatic 429/recovering/provider retry.
                raise ValueError("ACCEPTANCE_HTTP_" + str(response.status_code))
            for block in response.iter_bytes(32768):
                if len(body) + len(block) > 2 * 1024**2:
                    raise ValueError("ACCEPTANCE_RESPONSE_LIMIT")
                body.extend(block)
            headers = dict(response.headers)
        if not body:
            return None, headers
        if "text/event-stream" in headers.get("content-type", ""):
            messages = [
                json.loads(line[6:])
                for line in body.decode().splitlines()
                if line.startswith("data: ")
            ]
            value = next(m for m in messages if m.get("id") is not None)
        else:
            value = json.loads(body)
        return value, headers

    def mcp(self, name, args):
        if not self.initialized:
            value, headers = self.request(
                "POST",
                "/mcp",
                headers=self.headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 0,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "company-cohort-acceptance",
                            "version": "1",
                        },
                    },
                },
            )
            if "result" not in value:
                raise ValueError("ACCEPTANCE_MCP_INITIALIZE")
            if "mcp-session-id" in headers:
                self.headers["Mcp-Session-Id"] = headers["mcp-session-id"]
            self.request(
                "POST",
                "/mcp",
                headers=self.headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            self.initialized = True
        self.sequence += 1
        value, _ = self.request(
            "POST",
            "/mcp",
            headers=self.headers,
            json={
                "jsonrpc": "2.0",
                "id": self.sequence,
                "method": "tools/call",
                "params": {"name": name, "arguments": args},
            },
        )
        result = value.get("result") or {}
        if not result or result.get("isError"):
            raise ValueError("ACCEPTANCE_MCP_ERROR")
        return result.get("structuredContent") or json.loads(
            next(v["text"] for v in result["content"] if v["type"] == "text")
        )

    def verify(self, case, step, version):
        entity = case["expected"]["entity_id"]
        if step == "rest":
            envelope, _ = self.request(
                "GET",
                "/api/v1/companies/" + quote(entity, safe=""),
                params={"view": "latest_observed", "version": version},
            )
        elif step == "mcp":
            envelope = self.mcp(
                "hk_company_get",
                {"entityId": entity, "view": "latest_observed", "version": version},
            )
        else:
            raise ValueError("ACTUAL_BROWSER_EVIDENCE_REQUIRED")
        verify_company_record(envelope, case, version)
        path = self.folder / (sha(case["id"].encode()) + "-" + step + ".json")
        with path.open("xb") as out:
            out.write(canonical(envelope) + b"\n")
        return [path]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    plan = company_plan(json.loads(Path(args.cohort).read_text()))
    folder = Path(args.folder) / plan["version"]
    journal = Journal(folder / "progress.sqlite3", plan)
    verifier = PublicVerifier(folder / "responses")
    try:
        journal.run(verifier.verify, limit=args.limit, steps={"rest", "mcp"})
    finally:
        verifier.client.close()
    print(json.dumps(journal.summary()))


if __name__ == "__main__":
    main()
