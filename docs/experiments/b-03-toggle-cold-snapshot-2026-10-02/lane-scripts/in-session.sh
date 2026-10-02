#!/usr/bin/env bash
# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-03/bin/.
# in-session.sh <script.py> [args...]: run a B-03 harness script with the lane jev-use venv,
# inside cua-x11-session.sh. Records DISPLAY, UTC start and loadavg for the block log.
set -uo pipefail
WT=<lanes>/w3-b03-cold-snapshot
JEV=$WT/libs/cua-driver/examples/jev-use
export JEV_USE_DIR=$JEV
export PYTHONDONTWRITEBYTECODE=1
echo "[b03] DISPLAY=${DISPLAY:-unset} start_utc=$(date -u +%FT%T.%3NZ) loadavg=$(cat /proc/loadavg) telemetry_env=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset}" >&2
cd "$WT/docs/experiments/b-03-toggle-cold-snapshot-2026-10-02"
"$JEV/.venv/bin/python" "$@"; rc=$?
echo "[b03] end_utc=$(date -u +%FT%T.%3NZ) rc=$rc" >&2
exit $rc
