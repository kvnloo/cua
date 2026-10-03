#!/usr/bin/env bash
# One REAL block under the shared quiet-lane lock, inside a private X11 session.
# Invoked as:  hostless flock -s <quiet-lane.lock> locked_block.sh <ledger> <topology> <row> <block> <attempts> <out> [--forged]
# The lock is already held when this script starts; the receipt is appended before it exits
# (released_utc = end of work under the lock). Environment (set by the caller):
#   OWN36_LANES  lanes root (cua-x11-session.sh), OWN36_PYTHON (system python with gi),
#   OWN36_DRIVER, OWN36_FIXTURE, OWN36_WORKROOT, OWN36_SCRUB
set -uo pipefail
ledger=$1 topology=$2 row=$3 block=$4 attempts=$5 out=$6 forged=${7:-}
here="$(cd "$(dirname "$0")" && pwd)"
work="$OWN36_WORKROOT/$topology-$row-$block"
mkdir -p "$work"
acquired=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
before=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); before=${before:-0}
CUA_SESSION_ATSPI=1 \
CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 DO_NOT_TRACK=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 OWN36_DRIVER=$OWN36_DRIVER OWN36_FIXTURE=$OWN36_FIXTURE OWN36_WORK=$work OWN36_SCRUB=$OWN36_SCRUB OWN36_PYTHON=$OWN36_PYTHON" \
  "$OWN36_LANES/cua-x11-session.sh" "$OWN36_PYTHON" "$here/run_block.py" \
  --topology "$topology" --row "$row" --block "$block" --attempts "$attempts" --out "$out" $forged \
  > "$work/session.log" 2>&1
rc=$?
after=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); after=${after:-0}
released=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
printf '{"lock":"quiet-lane.lock","mode":"shared","topology":"%s","row":"%s","block":"%s","attempts_requested":"%s","attempts_recorded":%d,"forged":%s,"acquired_utc":"%s","released_utc":"%s","rc":%d}\n' \
  "$topology" "$row" "$block" "$attempts" "$((after - before))" "$( [ -n "$forged" ] && echo true || echo false)" "$acquired" "$released" "$rc" >> "$ledger"
exit $rc
