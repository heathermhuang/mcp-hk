#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")/../.."
exec 9>/run/lock/mcp-hk-sfc.lock
flock -n 9 || { echo 'SFC source cycle already owns its lock'; exit 0; }
available=$(df -Pk /srv/mcp-hk-curated | awk 'NR==2 {print $4}')
[ "$available" -ge 20971520 ] || { echo 'SFC held: 20 GiB host reserve'; exit 1; }
memory=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
[ "$memory" -ge 1048576 ] || { echo 'SFC held: 1 GiB memory reserve'; exit 1; }
exec python3 deploy/curated/sfc-job.py "$@"
