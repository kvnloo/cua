#!/usr/bin/env bash
# FIX-03 copy of harness/a3/qlock.sh (RECERT-FIX a3): lane name FIX-03 and a hard 300 s hold cap.
# qlock_fix03.sh shared <label> <packet-ledger> <cmd...>
# Holds the SHARED quiet-lane lock (flock -s) for the whole command and writes one receipt line to the
# packet ledger AND the loop-wide ledger. A shared acquisition first yields (up to 120 s) to any
# queued EXCLUSIVE waiter (another lane's timing phase). The command runs under `timeout 300`, so no
# hold exceeds 300 s; a block cut by the cap keeps every recorded cell (rc 124 in the receipt).
set -euo pipefail
mode="$1"; label="$2"; ledger="$3"; shift 3
[ "$mode" = shared ] || { echo "FIX-03 takes only the shared quiet-lane lock" >&2; exit 64; }
LOCKDIR="${CUA_LANE_LOCKDIR:?set CUA_LANE_LOCKDIR to the shared lock dir}"; GLOBAL="$LOCKDIR/quiet-lane-ledger.jsonl"
ino=$(stat -c %i "$LOCKDIR/quiet-lane.lock" 2>/dev/null || echo none)
yield_start=$(date +%s)
while grep -qE "^[0-9]+: -> FLOCK +ADVISORY +WRITE .*:${ino} " /proc/locks && [ $(( $(date +%s) - yield_start )) -lt 120 ]; do sleep 1; done
yield_s=$(( $(date +%s) - yield_start ))
exec 9>"$LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(cut -d' ' -f1-3 /proc/loadavg)"; t0=$(date +%s)
set +e; timeout --signal=TERM --kill-after=10 300 "$@"; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"; held=$(( $(date +%s) - t0 ))
line=$(printf '{"lane":"FIX-03","label":"%s","mode":"%s","pid":%d,"acquired":"%s","released":"%s","held_s":%d,"rc":%d,"loadavg_at_acquire":"%s","yield_s":%d,"cmd_sha256":"%s"}' \
  "$label" "$mode" "$$" "$acq" "$rel" "$held" "$rc" "$la_acq" "$yield_s" "$(printf '%s\0' "$@" | sha256sum | cut -c1-16)")
printf '%s\n' "$line" >> "$ledger"
printf '%s\n' "$line" >> "$GLOBAL"
exit "$rc"
