#!/usr/bin/env bash
# One REAL block under the shared quiet-lane lock, inside a private X11 session.
# Invoked as:  hostless flock -s <cargo-build.lock> flock -s <quiet-lane.lock> \
#                locked_block.sh <ledger> <topology> <row> <block> <attempts> <out> [run_block flags...]
# The locks are already held when this script starts (cargo lock first, then the quiet lane); the
# receipt is appended before it exits (released_utc = end of work under the lock). Environment (set
# by the caller):
#   OWN36_LANES  lanes root (cua-x11-session.sh), OWN36_PYTHON (system python with gi),
#   OWN36_DRIVER, OWN36_FIXTURE, OWN36_WORKROOT, OWN36_SCRUB
# RECERT-FIX copy of the OWN-36/FIX-02 wrapper: every argument after <out> is forwarded to
# run_block.py (--forged, --i5p-order X); the receipt also records them, the Driver sha256, the
# 1-minute loadavg at acquisition and the cargo-lock mode; it is appended to the packet ledger and to
# RECERT_GLOBAL_LEDGER (the loop-wide quiet-lane ledger) when set.
set -uo pipefail
ledger=$1 topology=$2 row=$3 block=$4 attempts=$5 out=$6
shift 6
extra=("$@")
forged=false
for a in "${extra[@]}"; do [ "$a" = --forged ] && forged=true; done
here="$(cd "$(dirname "$0")" && pwd)"
work="$OWN36_WORKROOT/$topology-$row-$block"
mkdir -p "$work"
acquired=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
la="$(cut -d' ' -f1-3 /proc/loadavg)"
before=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); before=${before:-0}
CUA_SESSION_ATSPI=1 \
CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 DO_NOT_TRACK=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 OWN36_DRIVER=$OWN36_DRIVER OWN36_FIXTURE=$OWN36_FIXTURE OWN36_WORK=$work OWN36_SCRUB=$OWN36_SCRUB OWN36_PYTHON=$OWN36_PYTHON" \
  "$OWN36_LANES/cua-x11-session.sh" "$OWN36_PYTHON" "$here/run_block.py" \
  --topology "$topology" --row "$row" --block "$block" --attempts "$attempts" --out "$out" "${extra[@]}" \
  > "$work/session.log" 2>&1
rc=$?
after=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); after=${after:-0}
released=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
line=$(printf '{"lane":"RECERT-FIX","lock":"quiet-lane.lock","mode":"shared","cargo_lock":"%s","topology":"%s","row":"%s","block":"%s","attempts_requested":"%s","attempts_recorded":%d,"forged":%s,"extra":"%s","driver_sha256":"%s","acquired_utc":"%s","released_utc":"%s","loadavg_at_acquire":"%s","rc":%d}' \
  "${RECERT_CARGO_LOCK_MODE:-none}" "$topology" "$row" "$block" "$attempts" "$((after - before))" "$forged" \
  "${extra[*]:-}" "$(sha256sum "$OWN36_DRIVER" | cut -c1-64)" "$acquired" "$released" "$la" "$rc")
printf '%s\n' "$line" >> "$ledger"
[ -n "${RECERT_GLOBAL_LEDGER:-}" ] && printf '%s\n' "$line" >> "$RECERT_GLOBAL_LEDGER"
exit $rc
