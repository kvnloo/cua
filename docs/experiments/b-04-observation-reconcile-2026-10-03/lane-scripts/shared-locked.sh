#!/usr/bin/env bash
# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-04/attempt-2/bin/.
# shared-locked.sh <label> <cmd...>: run a pilot/smoke/positive-control block under the SHARED
# quiet-lane lock and append a receipt line to the quiet-lane ledger (lane, label, mode "shared",
# pid, acquired, released, rc, loadavg_at_acquire), mirroring bin/quiet-timed.
set -euo pipefail
LOCKDIR=<lane-tmp>/locks; LEDGER="$LOCKDIR/quiet-lane-ledger.jsonl"
label="$1"; shift
exec 9>>"$LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
set +e; "$@"; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"
printf '{"lane":"B-04","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$label" "$$" "$acq" "$rel" "$rc" "$la" >> "$LEDGER"
exit "$rc"
