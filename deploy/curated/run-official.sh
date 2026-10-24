#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
mode=${1:-freshness}
case "$mode" in freshness|backfill|addresses|publish|plan) ;; *) exit 2;; esac
if [ "$mode" = backfill ] && systemctl is-active --quiet mcp-hk-official.service; then echo 'Backfill skipped: freshness unit owns the window'; exit 0; fi
available=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$available" -ge 10485760 ] || { echo 'Official ingestion blocked: less than 10 GiB free'; exit 1; }
memory=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
[ "$memory" -ge 1048576 ] || { echo 'Official ingestion blocked: less than 1 GiB available memory'; exit 1; }
image=$(docker compose -p curated -f deploy/curated/production.compose.yaml images -q backend)
# Timer provenance is independently checked against LastTriggerUSecMonotonic.
# An operator starting the unit outside its timer window receives a manual timestamp.
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "$mode" = freshness ]; then
    trigger=$(systemctl show mcp-hk-official.timer -p LastTriggerUSecMonotonic --value)
    uptime=$(awk '{printf "%.0f",$1*1000000}' /proc/uptime)
    if [ "${trigger:-0}" -gt 0 ] && [ "$((uptime-trigger))" -ge 0 ] && [ "$((uptime-trigger))" -lt 60000000 ]; then
        stamp=$(date -u +%Y-%m-%dT05:00:00Z)
    fi
fi
receipt=$(mktemp)
trap 'rm -f "$receipt"' EXIT HUP INT TERM
result=0
docker run --rm --memory 512m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_ingest "$mode" --scheduled-for "$stamp" > "$receipt" || result=$?
python3 - "$receipt" <<'PY'
import json,sys
try:
 r=json.load(open(sys.argv[1]))
except (ValueError,OSError):
 r={'status':'interrupted_or_unknown','backupStatus':'not_observed'}
print(json.dumps({k:r.get(k) for k in ('status','jobId','operation','requests','bytes','published','publicationStatus','backupStatus')}))
PY
# Publication and backup settle independently, even when a source family failed.
job=$(python3 - "$receipt" <<'PYJOB'
import json,sys
try: print(json.load(open(sys.argv[1])).get('jobId',''))
except (ValueError,OSError): print('')
PYJOB
)
if [ "$mode" != plan ]; then
    outcome=local_verified
    "$PWD/deploy/curated/backup-official.sh" || outcome=local_failed
    sha=$(cat /srv/mcp-hk-curated/official-backups/latest-local.sha256 2>/dev/null || true)
    if [ -n "$job" ]; then
    docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_health backup --job-id "$job" --outcome "$outcome" --sha256 "$sha"
    fi
    [ "$outcome" = local_verified ] || result=1
fi
exit "$result"
