#!/usr/bin/env bash
# usage (inside cua-x11-session.sh only): probe_then.sh <cmd> [args...]
# Session trust probe before any trial: the private display must answer xdpyinfo. A failed probe
# exits 97 (failed session block: kept, excluded, re-run under a new chunk id).
set -uo pipefail
if ! xdpyinfo >/dev/null 2>&1; then
  echo "[r2-07d] xdpyinfo probe FAILED on DISPLAY=${DISPLAY:-unset}" >&2
  exit 97
fi
echo "[r2-07d] xdpyinfo probe ok DISPLAY=$DISPLAY"
exec "$@"
