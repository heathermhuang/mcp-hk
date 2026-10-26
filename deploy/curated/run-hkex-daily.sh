#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
exec 9>/run/lock/mcp-hk-hkex-daily.lock
flock -n 9 || { echo 'HKEX updater already owns this occurrence'; exit 0; }
available=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$available" -ge 20971520 ] || { echo 'HKEX updater held: 20 GiB host reserve'; exit 1; }
memory=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
[ "$memory" -ge 1048576 ] || { echo 'HKEX updater held: 1 GiB memory reserve'; exit 1; }
exec python3 deploy/curated/hkex-daily-job.py
