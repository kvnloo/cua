#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless): locked.sh <locks-dir> <label> <cmd...>
# Runs <cmd> under the quiet-lane lock in SHARED mode and appends one receipt (lane OWN-20P) to the
# quiet-lane ledger. Used for version reads and the verifier; nothing timed here is a result.
set -uo pipefail
LOCKS="$1"; LABEL="$2"; shift 2
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
exec 8>"$LOCKS/quiet-lane.lock"; flock -s 8
acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
"$@"; rc=$?
rel="$(date -u +%FT%T.%3NZ)"
printf '{"lane":"OWN-20P","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$LABEL" "$$" "$acq" "$rel" "$rc" "$la" >> "$LOCKS/quiet-lane-ledger.jsonl"
exit $rc
