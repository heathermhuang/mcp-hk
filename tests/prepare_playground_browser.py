"""Seed local invented source data through the real parser/cache; no provider calls."""

import asyncio
import json
import os

from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk import resources


def main():
    service = Service(Store(os.environ["MCP_HK_DATABASE"]))
    service.resources.catalogue.publish(
        [
            {
                "id": "playground-fixture",
                "title": "Local precision fixture",
                "catalogue": "DATA.GOV.HK",
                "provider": "Example Department",
                "providerType": "government",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/fixture",
                "referencePeriod": "2025",
            }
        ],
        [
            {
                "id": "playground-source",
                "datasetId": "playground-fixture",
                "format": "JSON",
                "url": "https://example.gov.hk/fixture.json",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/fixture",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
                "aliases": [{"name": "Local precision fixture"}],
            },
            {
                "id": "playground-wide-source",
                "datasetId": "playground-fixture",
                "format": "JSON",
                "url": "https://example.gov.hk/wide.json",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/fixture",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
                "aliases": [{"name": "Local wide/nested fixture"}],
            },
        ],
        {},
    )
    rows = [
        {"name": "Exact large integer 中文", "n": 9007199254740993, "code": "00005"},
        {"name": "Integer", "n": 1, "code": "00005"},
        {"name": "Float", "n": 1.0, "code": "00005"},
        {"name": "Boolean", "n": True, "code": "00005"},
        {"name": "Null", "n": None, "code": "00005"},
        {"name": "Missing", "code": "00005"},
    ] + [{"name": f"Row {i}", "n": i + 10, "code": "00005"} for i in range(20)]

    wide = [
        {
            **{f"f{k:03d}": "source text " + "中" * 35 for k in range(95)},
            "id": f"wide-{i:04d}",
            "name": f"Wide row {i:04d}",
            "nested": {"x": "nested source text", "n": i},
        }
        for i in range(80)
    ]

    async def fixture(url, *args, **kwargs):
        return (
            json.dumps(
                wide if url.endswith("wide.json") else rows, ensure_ascii=False
            ).encode(),
            {},
            url,
            200,
        )

    resources.fetch = fixture
    asyncio.run(service.resources.query("playground-source"))
    asyncio.run(service.resources.query("playground-wide-source"))


if __name__ == "__main__":
    main()
