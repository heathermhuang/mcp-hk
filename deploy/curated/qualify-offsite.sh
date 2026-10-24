#!/bin/sh
set -eu
exec "$(dirname "$0")/run-offsite.sh" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" qualification
