#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
stamp=$(date -u +%Y-%m-%dT05:00:00Z)
# Health persists a receipt, so it must not race a dump's full-state fingerprints.
exec 9>"${MCP_HK_MAINTENANCE_LOCK:-/run/lock/mcp-hk-official-maintenance.lock}"
if ! flock -s -n 9; then
 printf '%s' "$stamp" > /srv/mcp-hk-curated/official-health-running
 printf '{"status":"maintenance_running","verificationDeferred":true,"scheduledFor":"%s"}\n' "$stamp"
 exit 0
fi
image=$(docker compose -p curated -f deploy/curated/production.compose.yaml images -q backend)
# Also recheck an actual recovery-state change after an earlier failed check.
if [ "$(date -u +%H)" = 06 ] && [ "$(cat /srv/mcp-hk-curated/official-health-running 2>/dev/null || true)" != "$stamp" ]; then
 needed=$(docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_health recheck-needed --scheduled-for "$stamp")
 if ! printf '%s' "$needed" | python3 -c 'import json,sys; sys.exit(not json.load(sys.stdin)["recheckNeeded"])'; then exit 0; fi
fi
receipt=$(mktemp)
trap 'rm -f "$receipt"' EXIT HUP INT TERM
result=0
docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_health verify --scheduled-for "$stamp" > "$receipt" || result=$?
cat "$receipt"
if python3 -c 'import json,sys; sys.exit(json.load(open(sys.argv[1]))["status"] not in ("running","recovery_running"))' "$receipt"; then printf '%s' "$stamp" > /srv/mcp-hk-curated/official-health-running; fi
exit "$result"
