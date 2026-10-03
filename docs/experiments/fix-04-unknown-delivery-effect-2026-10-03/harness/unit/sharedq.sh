#!/usr/bin/env bash
# FIX-04: run a CPU-heavy build or unit step under the SHARED quiet-lane lock (so it never overlaps
# another lane's EXCLUSIVE timing phase), after yielding up to 120 s to a queued exclusive waiter, and
# write one receipt line to the packet ledger and the loop-wide ledger (as qlock_fix04.sh, without
# the 300 s hold cap: the caller's own timeout bounds the step).
# usage: sharedq.sh <label> <packet-ledger> <cmd...>
set -euo pipefail
label="$1"; ledger="$2"; shift 2
LOCKDIR="${CUA_LANE_LOCKDIR:?set CUA_LANE_LOCKDIR}"; GLOBAL="$LOCKDIR/quiet-lane-ledger.jsonl"
ino=$(stat -c %i "$LOCKDIR/quiet-lane.lock" 2>/dev/null || echo none)
yield_start=$(date +%s)
while grep -qE "^[0-9]+: -> FLOCK +ADVISORY +WRITE .*:${ino} " /proc/locks && [ $(( $(date +%s) - yield_start )) -lt 120 ]; do sleep 1; done
yield_s=$(( $(date +%s) - yield_start ))
exec 9>"$LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(cut -d' ' -f1-3 /proc/loadavg)"; t0=$(date +%s)
set +e; "$@"; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"; held=$(( $(date +%s) - t0 ))
line=$(printf '{"lane":"FIX-04","label":"%s","mode":"shared","kind":"build_or_unit","pid":%d,"acquired":"%s","released":"%s","held_s":%d,"rc":%d,"loadavg_at_acquire":"%s","yield_s":%d}' \
  "$label" "$$" "$acq" "$rel" "$held" "$rc" "$la_acq" "$yield_s")
printf '%s\n' "$line" >> "$ledger"
printf '%s\n' "$line" >> "$GLOBAL"
exit "$rc"
