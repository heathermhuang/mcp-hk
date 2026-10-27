#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
# The existing paid host policy is metadata only; no provider credential is used.
if ! python3 - <<'PYPOLICY'
import datetime,json,os
p=json.load(open(os.environ.get('MCP_HK_MAINTENANCE_POLICY','/etc/mcp-hk-curated/maintenance-policy.json')))
n=datetime.datetime.now(datetime.timezone.utc)
assert p['providerBackupWeekdayUtc'] in ['MON','TUE','WED','THU','FRI','SAT','SUN']
inside=n.strftime('%a').upper()==p['providerBackupWeekdayUtc'] and p['providerBackupStartHourUtc']<=n.hour<p['providerBackupEndHourUtc']
raise SystemExit(1 if inside else 0)
PYPOLICY
then echo 'Backfill held: provider maintenance window or missing policy'; exit 0; fi
image=$(python3 deploy/curated/backend-image.py)
checkpoint=$(docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_backfill_checkpoint)
if printf '%s' "$checkpoint" | python3 -c 'import json,sys; raise SystemExit(not json.load(sys.stdin)["noOp"])'; then echo 'Backfill unchanged: no backlog or new milestone'; exit 0; fi
result=0
if printf '%s' "$checkpoint" | python3 -c 'import json,sys; raise SystemExit(json.load(sys.stdin)["pendingPairs"]<=0)'; then ./deploy/curated/run-official.sh backfill || result=$?; fi
checkpoint=$(docker run --rm --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_backfill_checkpoint)
printf '%s\n' "$checkpoint"
if printf '%s' "$checkpoint" | python3 -c 'import json,sys; raise SystemExit(json.load(sys.stdin)["milestoneNeeded"] is None)'; then
 systemctl start --no-block mcp-hk-official-milestone.service
fi

exit "$result"
