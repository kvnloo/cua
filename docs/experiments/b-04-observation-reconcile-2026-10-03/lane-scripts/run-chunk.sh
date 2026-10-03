#!/usr/bin/env bash
# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-04/attempt-2/bin/.
# run-chunk.sh <label> <rounds-from> <rounds-to> [block]: one measured chunk = one EXCLUSIVE quiet-lane
# acquisition (bin/quiet-timed writes the ledger receipt), private Xvfb session, binary R, tail injection.
# Invoke as: TMPDIR=<lane-tmp>/w4a2-b04 hostless run-chunk.sh ...
set -euo pipefail
L=<lanes>
B=$L/artifacts/r2/B-04/attempt-2/bin
export TMPDIR=<lane-tmp>/w4a2-b04
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1 B04_LOCK=exclusive B04_LOCK_LABEL=$1"
exec "$L/bin/quiet-timed" "$1" "$L/cua-x11-session.sh" "$B/in-session.sh" run_b04.py \
  --driver "$L/bin/cua-driver-r2-10-8f3a646b4" --out "$TMPDIR/measured" --plan measured \
  --rounds-from "$2" --rounds-to "$3" --inject-mode tail --block "${4:-m}"
