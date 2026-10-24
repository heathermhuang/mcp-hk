#!/usr/bin/env bash
set -euo pipefail
cat <<'HELP'
The old unlocked installer is retired. Use the locked development environment:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.lock
  .venv/bin/python -m pip install --no-deps -e .
For stdio clients use .venv/bin/mcp-hk; for HTTP use .venv/bin/mcp-hk-http.
See CONTRIBUTING.md and docs/production.md. This helper installs nothing.
HELP
