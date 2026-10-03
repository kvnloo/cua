#!/usr/bin/env bash
# FIX-05 SHARED quiet-lane wrapper (pattern of FIX-04 harness/qlock_fix04.sh and unit/sharedq.sh; bin/quiet-shared
# is not installed). Holds the quiet-lane lock in SHARED mode (flock -s) for one command, with the lock fd CLOSED for
# the command and its children (9>&-), so no child process can keep the lock alive after the wrapper exits.
# Before acquiring it yields while /proc/locks shows a queued EXCLUSIVE waiter on the quiet-lane.lock inode (up to
# FQ_YIELD_MAX s, default 600). The command runs under `timeout <cap>` (blocks: 300 s; builds/units: caller's cap).
# One receipt line ('mode':'shared') goes to the packet ledger AND the loop-wide ledger.
# usage: qlock_fix05.sh <label> <packet-ledger> <cap-seconds> <cmd...>
set -euo pipefail
label="$1"; ledger="$2"; cap="$3"; shift 3
LOCKDIR="${CUA_LANE_LOCKDIR:?set CUA_LANE_LOCKDIR to the shared lock dir}"; GLOBAL="$LOCKDIR/quiet-lane-ledger.jsonl"
ino=$(stat -c %i "$LOCKDIR/quiet-lane.lock")
yield_start=$(date +%s)
while grep -qE "^[0-9]+: -> FLOCK +ADVISORY +WRITE .*:${ino} " /proc/locks \
      && [ $(( $(date +%s) - yield_start )) -lt "${FQ_YIELD_MAX:-600}" ]; do sleep 1; done
yield_s=$(( $(date +%s) - yield_start ))
exec 9>"$LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(cut -d' ' -f1-3 /proc/loadavg)"; t0=$(date +%s)
set +e; timeout --signal=TERM --kill-after=10 "$cap" "$@" 9>&-; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"; held=$(( $(date +%s) - t0 ))
exec 9>&-
line=$(printf '{"lane":"FIX-05","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","held_s":%d,"cap_s":%d,"rc":%d,"loadavg_at_acquire":"%s","yield_s":%d,"cmd_sha256":"%s"}' \
  "$label" "$$" "$acq" "$rel" "$held" "$cap" "$rc" "$la_acq" "$yield_s" "$(printf '%s\0' "$@" | sha256sum | cut -c1-16)")
printf '%s\n' "$line" >> "$ledger"
printf '%s\n' "$line" >> "$GLOBAL"
exit "$rc"
