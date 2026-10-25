"""Private read services must not initialize the public gateway on import."""

import os
import subprocess
import sys


def test_private_backend_import_does_not_create_gateway_state(tmp_path):
    database = tmp_path / "unexpected-gateway.sqlite3"
    env = dict(os.environ, MCP_HK_DATABASE=str(database))
    script = (
        "import sys; import mcp_open_data_hk.curated.backend; "
        "assert 'mcp_open_data_hk.server' not in sys.modules, 'gateway eagerly imported'"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert not database.exists()


def test_legacy_mcp_export_remains_available_on_explicit_import(tmp_path):
    env = dict(os.environ, MCP_HK_DATABASE=str(tmp_path / "gateway.sqlite3"))
    script = (
        "from mcp_open_data_hk import mcp; "
        "from mcp_open_data_hk.server import mcp as server; assert mcp is server"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
