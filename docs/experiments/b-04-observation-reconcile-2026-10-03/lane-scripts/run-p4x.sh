#!/usr/bin/env bash
# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-04/attempt-2/bin/.
# run-p4x.sh <label> [rounds-from] [rounds-to]: the P4 Williams extension block "x" (added after the
# measured run to fix the P4 order defect; disclosed). One EXCLUSIVE quiet-lane acquisition
# (bin/quiet-timed writes the ledger receipt), private Xvfb session, binary R, no injection.
# Invoke as: TMPDIR=<lane-tmp>/w4a2-b04 hostless run-p4x.sh ...  (refuses outside hostless)
set -euo pipefail
[ "${CUA_HOSTLESS:-}" = "1" ] || { echo "refusing: run under bin/hostless" >&2; exit 97; }
L=<lanes>
B=$L/artifacts/r2/B-04/attempt-2/bin
export TMPDIR=<lane-tmp>/w4a2-b04
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1 B04_LOCK=exclusive B04_LOCK_LABEL=$1 B04_HOSTLESS=$CUA_HOSTLESS"
exec "$L/bin/quiet-timed" "$1" "$L/cua-x11-session.sh" "$B/in-session.sh" run_b04.py \
  --driver "$L/bin/cua-driver-r2-10-8f3a646b4" --out "$TMPDIR/p4x" --plan p4x \
  --rounds-from "${2:-0}" --rounds-to "${3:-30}" --block x
