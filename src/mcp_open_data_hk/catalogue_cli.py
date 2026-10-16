"""Ordinary operator jobs: no model calls and no public mutation tools."""

import argparse
import asyncio
import json
import os

from .catalogue_store import CatalogueStore
from .catalogue_sync import sync
from .resources import Resources
from .storage import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["sync", "audit", "coverage"])
    parser.add_argument("--batch", type=int, default=20)
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 1000:
        parser.error("cycles must be 1..1000")
    store = Store(os.environ.get("MCP_HK_DATABASE", ".data/mcp-hk.sqlite3"))
    if args.operation == "sync":
        result = asyncio.run(sync(store))
    elif args.operation == "audit":

        async def audit():
            resources = Resources(store)
            for _ in range(args.cycles):
                receipt = await resources.audit(args.batch)
                print(json.dumps(receipt), flush=True)
                if receipt["cycleComplete"]:
                    break
            return resources.catalogue.coverage()

        result = asyncio.run(audit())
    else:
        result = CatalogueStore(store).coverage()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
