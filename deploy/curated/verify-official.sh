#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
stamp=$(date -u +%Y-%m-%dT05:00:00Z)
# The second check is useful only if the owning unit was still running at 05:20.
if [ "$(date -u +%H)" = 06 ] && [ "$(cat /srv/mcp-hk-curated/official-health-running 2>/dev/null || true)" != "$stamp" ]; then exit 0; fi
image=$(docker compose -p curated -f deploy/curated/production.compose.yaml images -q backend)
receipt=$(mktemp)
trap 'rm -f "$receipt"' EXIT HUP INT TERM
result=0
docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_health verify --scheduled-for "$stamp" > "$receipt" || result=$?
cat "$receipt"
if python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1]))["status"]!="running")' "$receipt"; then printf '%s' "$stamp" > /srv/mcp-hk-curated/official-health-running; fi
exit "$result"
