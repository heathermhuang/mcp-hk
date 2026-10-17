"""Live verification must exercise MCP even when the independent HTTP path fails."""

import importlib.util
import json
from pathlib import Path

import pytest


def test_live_probe_records_both_failed_protocols(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "scripts" / "verify_transport.py"
    spec = importlib.util.spec_from_file_location("verify_transport", path)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    calls = []

    def read(url, body=None, mcp=False):
        calls.append((url, body, mcp))
        if mcp:
            return {
                "result": {
                    "isError": True,
                    "content": [{"text": "SOURCE_NOT_FOUND: Source returned HTTP 404"}],
                }
            }, ""
        return {"error": {"code": "SOURCE_NOT_FOUND"}}, "Cache-Control: no-store"

    monkeypatch.setattr(probe, "read", read)
    out = tmp_path / "receipt.json"
    monkeypatch.setattr(
        "sys.argv",
        ["probe", "--mcp", "--only", "Fortune-Ferry,Water-Taxi", "--out", str(out)],
    )
    with pytest.raises(SystemExit) as result:
        probe.main()
    assert result.value.code == 1
    assert [call[2] for call in calls] == [False, True, False, True]
    receipts = json.loads(out.read_text())["results"]
    assert len(receipts) == 2
    for receipt in receipts:
        assert receipt["status"] == "failed"
        for protocol in ["http", "mcp"]:
            assert receipt[protocol]["status"] == "failed"
            assert "SOURCE_NOT_FOUND" in receipt[protocol]["error"]
