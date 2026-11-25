"""The metering names must match the public production discovery posture."""

import json
from pathlib import Path

import pytest
from fastmcp import Client

from mcp_open_data_hk.server import create_server
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.mark.asyncio
async def test_metering_matches_production_tool_registry(monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://curated.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "test-only-" + "x" * 32)
    monkeypatch.setenv("MCP_HK_WEBB_SDI_ENABLED", "true")
    monkeypatch.setenv("MCP_HK_HKEX_DAILY_ENABLED", "true")
    monkeypatch.delenv("MCP_HK_SFC_POLICY_JSON", raising=False)
    monkeypatch.delenv("MCP_HK_SFC_POLICY_SHA256", raising=False)
    service = Service(Store(str(tmp_path / "registry.sqlite3")))
    monkeypatch.setattr(
        service.racing.store.profiles,
        "status",
        lambda: {"accepted": True, "modes": {"mcp": True}},
    )
    async with Client(create_server(service)) as client:
        registered = sorted(tool.name for tool in await client.list_tools())

    path = Path(__file__).parents[1] / "deploy/cloudflare/mcp-tool-names.json"
    assert json.loads(path.read_text()) == registered
