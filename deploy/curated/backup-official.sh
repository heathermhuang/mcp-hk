#!/bin/sh
set -eu
cd /opt/mcp-hk
export CURATED_HOSTNAME=curated.mcp.hk
folder=/srv/mcp-hk-curated/official-backups
install -d -m 700 "$folder"
postgres=$(docker compose -f deploy/curated/production.compose.yaml ps -q postgres)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
file="$folder/official-$stamp.dump"
# Metadata plus official captures/records/versions/runs/pointer. The immutable
# archival model has its separate existing offsite backup and unchanged exports.
(umask 077; set -C; docker exec "$postgres" pg_dump -U postgres -d curated -Fc --no-owner --no-acl -n curated > "$file")
sha256sum "$file" > "$file.sha256"
# Check the archive index before recording success. Release qualification also
# retrieves a fresh R2 copy and performs a full isolated database restore.
docker exec -i "$postgres" pg_restore --list < "$file" > /dev/null
find "$folder" -maxdepth 1 -type f -name 'official-????????T??????Z.dump*' -mtime +30 -delete
printf 'Official logical backup verified: %s\n' "$stamp"
