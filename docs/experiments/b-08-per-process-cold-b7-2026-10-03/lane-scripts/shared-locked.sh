#!/usr/bin/env bash
# shared-locked.sh <label> <cmd...>: run a pilot, a version read, the analyzer or the verifier under the SHARED quiet-lane lock and
# append a receipt line (lane, label, mode "shared", pid, acquired, released, rc, loadavg_at_acquire) to
# the quiet-lane ledger, mirroring bin/quiet-timed. Nothing timed here is reported as a result.
# Machine paths come from the environment: B08_LOCKDIR.
set -euo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LOCKDIR="${B08_LOCKDIR:?}"; LEDGER="$LOCKDIR/quiet-lane-ledger.jsonl"
label="$1"; shift
exec 9>>"$LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
set +e; "$@"; rc=$?; set -e
rel="$(date -u +%FT%T.%3NZ)"
printf '{"lane":"B-08","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$label" "$$" "$acq" "$rel" "$rc" "$la" >> "$LEDGER"
exit "$rc"
