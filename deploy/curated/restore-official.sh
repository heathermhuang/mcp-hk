#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
export CURATED_HOSTNAME=curated.mcp.hk
job=$1
[ "${#job}" -eq 32 ] || exit 2
case "$job" in *[!a-f0-9]*) exit 2;; esac
folder=/srv/mcp-hk-curated/official-offsite
database=official_maintenance_restore_$job
file=$folder/retrieved-$job.dump
[ -s "$file" ] || exit 1
size=$(stat -c %s "$file")
free=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$free" -ge "$((10485760+size/1024*20))" ] || { echo 'Restore headroom gate'; exit 1; }
image=$(docker compose -p curated -f deploy/curated/production.compose.yaml images -q backend)
docker exec curated-postgres-1 createdb -U postgres "$database"
docker exec -i curated-postgres-1 pg_restore -U postgres -d "$database" --exit-on-error --single-transaction --no-owner --no-acl < "$file"
# Logical dumps do not preserve planner statistics. Qualify a prepared restore,
# without racing asynchronous autovacuum or loosening the read latency gate.
docker exec curated-postgres-1 vacuumdb -U postgres -d "$database" --analyze-only --schema=curated
# Exact existing reader only. The restore name is derived from this owning job.
printf 'REVOKE ALL ON DATABASE "%s" FROM PUBLIC; GRANT CONNECT ON DATABASE "%s" TO curated_reader; GRANT USAGE ON SCHEMA curated TO curated_reader; GRANT SELECT ON ALL TABLES IN SCHEMA curated TO curated_reader;\n' "$database" "$database" | docker exec -i curated-postgres-1 psql -U postgres -d "$database" -v ON_ERROR_STOP=1 > /dev/null
if docker run --rm --user 0 --read-only --cap-drop ALL --memory 256m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/backend.env --mount type=bind,src="$folder",dst=/evidence,readonly "$image" python -m mcp_open_data_hk.curated.official_restore_check --database "$database" --source "/evidence/source-$job.json" --receipt "/evidence/receipt-$job.json" > "$folder/restore-$job.json"; then
 docker run --rm --user 0 --read-only --cap-drop ALL --memory 128m --cpus 1 --network curated_default --env-file /etc/mcp-hk-curated/owner.env --mount type=bind,src="$folder/restore-$job.json",dst=/proof.json,readonly "$image" python -m mcp_open_data_hk.curated.official_offsite_job qualify-restore --receipt /proof.json
 # Only this successfully checked disposable clone is removed; production, raw
 # captures, published versions, cursors and all offsite evidence remain untouched.
 docker exec curated-postgres-1 dropdb -U postgres "$database"
else
 echo 'Isolated restore/performance failed; retain the owning clone and receipts'
 exit 1
fi
