#!/bin/sh
set -eu
cd /opt/mcp-hk
export CURATED_HOSTNAME=curated.mcp.hk
available=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$available" -ge 10485760 ] || { echo 'Official ingestion blocked: less than 10 GiB free'; exit 1; }
image=$(docker compose -f deploy/curated/production.compose.yaml images -q backend)
docker run --rm --network curated_default --env-file /etc/mcp-hk-curated/owner.env "$image" python -m mcp_open_data_hk.curated.official_ingest
# Host logical backup plus already-enabled weekly provider backup coverage.
/opt/mcp-hk/deploy/curated/backup-official.sh
