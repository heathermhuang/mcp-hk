#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
root=$PWD
mode=${1:-all}
if [[ $# -gt 1 || ! $mode =~ ^(all|python|quality|worker)$ ]]; then
    echo 'Usage: scripts/check.sh [all|python|quality|worker]' >&2
    exit 2
fi

if [[ $mode != worker ]]; then
    python=${PYTHON:-$root/.venv/bin/python}
    if [[ ! -x $python ]]; then
        python=$(command -v "${PYTHON:-python3}")
    fi
    export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi

if [[ $mode == all || $mode == quality ]]; then
    "$python" -m black --check src/ tests/
    "$python" -m flake8 src/ tests/
fi
if [[ $mode == all || $mode == python ]]; then
    "$python" -m pytest tests/
fi
if [[ $mode == all || $mode == worker ]]; then
    export WRANGLER_SEND_METRICS=false
    cd deploy/cloudflare
    npm run types
    npm run check
    npm test
fi
