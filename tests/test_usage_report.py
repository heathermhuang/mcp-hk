import importlib.util
import json
from pathlib import Path
import stat
import sys

import pytest


spec = importlib.util.spec_from_file_location(
    "usage_report", Path(__file__).resolve().parents[1] / "scripts/usage_report.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_private_html_escapes_query_content_and_has_no_active_resources():
    rendered = report.render(
        {
            "keywords": [{"term": '<script>alert("x")</script>', "lower_bound": 2}],
            "definitions": {"scope": "bounded"},
        }
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "default-src &#" not in rendered
    assert "default-src 'none'" in rendered
    assert "https://" not in rendered


def test_saved_json_can_be_rendered_without_credentials(tmp_path, monkeypatch):
    source, output = tmp_path / "report.json", tmp_path / "report.html"
    source.write_text(json.dumps({"totals": {"requests": 7}}))
    monkeypatch.setattr(
        sys, "argv", ["usage_report", "--input", str(source), "--output", str(output)]
    )
    report.main()
    assert "requests" in output.read_text()
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_operator_redirects_cannot_forward_credentials():
    with pytest.raises(ValueError, match="redirects disabled"):
        report.NoRedirect().redirect_request(None, None, None, None)


def test_cross_origin_clients_can_send_the_opt_out_header(tmp_path):
    from fastapi.testclient import TestClient
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    with TestClient(
        create_app(Service(Store(str(tmp_path / "usage.sqlite3"))))
    ) as client:
        response = client.options(
            "/api/v1/catalogue/datasets",
            headers={
                "Origin": "https://mcp.hk",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-mcp-analytics-opt-out",
            },
        )
    assert response.status_code == 200
    assert "x-mcp-analytics-opt-out" in response.headers["access-control-allow-headers"]
