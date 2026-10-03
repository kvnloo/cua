#!/usr/bin/env bash
# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-04/attempt-2/bin/.
# in-session.sh <script.py> [args...] | --versions <driver>: run a B-04 (attempt 2) harness script with
# the lane jev-use venv, inside cua-x11-session.sh. Records DISPLAY, UTC start, loadavg and lock mode.
# hostless=: added for the P4X block (B04_HOSTLESS is passed in from run-p4x.sh, which refuses to run without CUA_HOSTLESS=1); the m-block chunks ran the line without it.
set -uo pipefail
WT=<lanes>/w4-a2-b04
JEV=$WT/libs/cua-driver/examples/jev-use
export JEV_USE_DIR=$JEV
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=<lane-tmp>/w4a2-b04
echo "[b04a2] DISPLAY=${DISPLAY:-unset} start_utc=$(date -u +%FT%T.%3NZ) loadavg=$(cat /proc/loadavg) telemetry_env=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset} lock=${B04_LOCK:-unset} wayland=${WAYLAND_DISPLAY:-unset} hostless=${B04_HOSTLESS:-unset}" >&2
if [ "${1:-}" = "--versions" ]; then
  echo "driver_version: $("$2" --version 2>&1 | head -1)"
  echo "driver_sha256: $(sha256sum "$2" | cut -d' ' -f1)"
  echo "google-chrome-stable: $(google-chrome-stable --version 2>&1 | head -1)"
  echo "chromium: $(chromium --version 2>&1 | head -1)"
  exit 0
fi
cd "$WT/docs/experiments/b-04-observation-reconcile-2026-10-03"
"$JEV/.venv/bin/python" "$@"; rc=$?
echo "[b04a2] end_utc=$(date -u +%FT%T.%3NZ) rc=$rc" >&2
exit $rc
