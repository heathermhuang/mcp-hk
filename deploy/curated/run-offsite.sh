#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
stamp=${1:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}
kind=${2:-qualification}
if [ "$#" -eq 0 ]; then
 trigger=$(busctl get-property org.freedesktop.systemd1 /org/freedesktop/systemd1/unit/mcp_2dhk_2dofficial_2doffsite_2etimer org.freedesktop.systemd1.Timer LastTriggerUSecMonotonic 2>/dev/null | sed -n 's/^t \([0-9][0-9]*\)$/\1/p')
 uptime=$(awk '{printf "%.0f",$1*1000000}' /proc/uptime)
 if [ "${trigger:-0}" -gt 0 ] && [ "$((uptime-trigger))" -ge 0 ] && [ "$((uptime-trigger))" -lt 60000000 ]; then
  kind=daily
  stamp=$(python3 -c 'from datetime import datetime,timedelta,timezone; n=datetime.now(timezone.utc); d=n.replace(hour=5,minute=17,second=0,microsecond=0); d=d-timedelta(days=1) if d>n else d; print(d.strftime("%Y-%m-%dT%H:%M:%SZ"))')
 fi
fi
case "$kind" in daily|qualification) ;; *) exit 2;; esac
exec 9>"${MCP_HK_MAINTENANCE_LOCK:-/run/lock/mcp-hk-official-maintenance.lock}"
flock -n 9 || { echo 'Official maintenance skipped: another owning host job'; exit 0; }
[ -s /etc/mcp-hk-curated/official-uploader.json ] || { echo 'Offsite capability not installed'; exit 1; }
[ "$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')" -ge 10485760 ] || exit 1
[ "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -ge 1048576 ] || exit 1
image=$(python3 deploy/curated/backend-image.py)
folder=/srv/mcp-hk-curated/official-offsite
install -d -m 700 "$folder"
start=$(docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_offsite_job begin --scheduled-for "$stamp")
job=$(printf '%s' "$start" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("jobId") or "")')
[ -n "$job" ] || { echo 'Duplicate offsite occurrence; retained prior outcome'; exit 0; }
outcome=offsite_failed
# The owning job remains unknown if interrupted. No trap settles an unknown upload.
if docker run --rm --memory 512m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_recovery --commit "$(cat .release-commit)" > "$folder/source-$job.json" && ./deploy/curated/backup-official.sh; then
    dump=$(ls -1t /srv/mcp-hk-curated/official-backups/official-*.dump | head -1)
    stable=0
    if ! docker run --rm --memory 512m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_recovery --commit "$(cat .release-commit)" > "$folder/source-check-$job.json"; then stable=1; fi
    if [ "$stable" -eq 0 ]; then
    python3 - "$folder/source-$job.json" "$folder/source-check-$job.json" <<'PYSTABLE' || stable=$?
import json,sys
assert json.load(open(sys.argv[1]))==json.load(open(sys.argv[2])), 'Backup checkpoint changed during dump'
PYSTABLE
    fi
    if [ "$stable" -eq 0 ] && docker run --rm --user 0 --read-only --tmpfs /tmp:rw,noexec,nosuid,size=8m --cap-drop ALL --security-opt no-new-privileges --memory 256m --cpus 1 --network curated_default --mount type=bind,src=/etc/mcp-hk-curated/official-uploader.json,dst=/config/uploader.json,readonly --mount type=bind,src="$folder",dst=/evidence --mount type=bind,src="$dump",dst=/backup/official.dump,readonly --mount type=bind,src="$folder/source-$job.json",dst=/backup/source.json,readonly "$image" python -m mcp_open_data_hk.curated.official_offsite --config /config/uploader.json --dump /backup/official.dump --source /backup/source.json --job-id "$job" --retrieved-dump "/evidence/retrieved-$job.dump" > "$folder/receipt-$job.json"; then outcome=offsite_verified; fi
fi
if [ "$outcome" = offsite_verified ]; then
 docker run --rm --user 0 --read-only --cap-drop ALL --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env --mount type=bind,src="$folder/receipt-$job.json",dst=/receipt.json,readonly "$image" python -m mcp_open_data_hk.curated.official_offsite_job finish --job-id "$job" --outcome "$outcome" --schedule-kind "$kind" --receipt /receipt.json
else
 docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_offsite_job finish --job-id "$job" --outcome "$outcome" --schedule-kind "$kind"
 exit 1
fi
if ! ./deploy/curated/restore-official.sh "$job"; then
 docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_offsite_job restore-failed --job-id "$job"
 exit 1
fi
printf 'Offsite receipt: %s\n' "$folder/receipt-$job.json"
# Bounded pruning is independent of backup success. It preserves unverified
# evidence and latest two copies, and requires a matching still-present R2 copy.
docker run --rm --user 0 --read-only --cap-drop ALL --memory 256m --cpus 1 --network curated_default --mount type=bind,src=/etc/mcp-hk-curated/official-uploader.json,dst=/config/uploader.json,readonly --mount type=bind,src="$folder",dst=/evidence "$image" python -m mcp_open_data_hk.curated.official_retention --folder /evidence --config /config/uploader.json || echo 'Retention held; all uncertain copies retained'
