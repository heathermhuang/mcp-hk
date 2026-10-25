#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
mode=${1:-freshness}
address_limit=${2:-20}
case "$address_limit" in ''|*[!0-9]*) exit 2;; esac
[ "$address_limit" -le 100 ] || exit 2
case "$mode" in freshness|backfill|addresses|publish|plan) ;; *) exit 2;; esac
if [ "$mode" = backfill ] && systemctl is-active --quiet mcp-hk-official.service; then echo 'Backfill skipped: freshness unit owns the window'; exit 0; fi
exec 9>"${MCP_HK_MAINTENANCE_LOCK:-/run/lock/mcp-hk-official-maintenance.lock}"
flock -n 9 || { echo 'Official maintenance skipped: another owning host job'; exit 0; }
available=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$available" -ge 10485760 ] || { echo 'Official ingestion blocked: less than 10 GiB free'; exit 1; }
memory=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
[ "$memory" -ge 1048576 ] || { echo 'Official ingestion blocked: less than 1 GiB available memory'; exit 1; }
image=$(docker compose -p curated -f deploy/curated/production.compose.yaml images -q backend)
if [ "$mode" = backfill ]; then
 if ! docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_offsite_job gate; then echo 'Backfill held: offsite recovery gate'; exit 0; fi
fi
if [ "$mode" = addresses ]; then
 remaining=$(docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_address_stage | python3 -c 'import json,sys; print(json.load(sys.stdin)["remaining"])')
 [ "$remaining" -gt 0 ] || { echo 'Address daily stage already settled'; exit 0; }
fi
# Timer provenance is independently checked against LastTriggerUSecMonotonic.
# An operator starting the unit outside its timer window receives a manual timestamp.
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
if [ "$mode" = freshness ]; then
    trigger=$(busctl get-property org.freedesktop.systemd1 /org/freedesktop/systemd1/unit/mcp_2dhk_2dofficial_2etimer org.freedesktop.systemd1.Timer LastTriggerUSecMonotonic 2>/dev/null | sed -n 's/^t \([0-9][0-9]*\)$/\1/p')
    uptime=$(awk '{printf "%.0f",$1*1000000}' /proc/uptime)
    if [ "${trigger:-0}" -gt 0 ] && [ "$((uptime-trigger))" -ge 0 ] && [ "$((uptime-trigger))" -lt 60000000 ]; then
        stamp=$(python3 -c 'from datetime import datetime,timedelta,timezone; n=datetime.now(timezone.utc); d=n.replace(hour=5,minute=0,second=0,microsecond=0); d=d-timedelta(days=1) if d>n else d; print(d.strftime("%Y-%m-%dT%H:%M:%SZ"))')
    fi
fi
receipt=$(mktemp)
trap 'rm -f "$receipt"' EXIT HUP INT TERM
result=0
docker run --rm --memory 512m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_ingest "$mode" --scheduled-for "$stamp" --address-limit "$address_limit" > "$receipt" || result=$?
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
