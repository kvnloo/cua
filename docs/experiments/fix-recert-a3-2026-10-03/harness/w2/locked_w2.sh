#!/usr/bin/env bash
# One W2 block (or smoke) under the shared quiet-lane lock, inside a private X11 session with AT-SPI.
# Pattern of harness/fix02-w3/native/locked_block.sh (wave-3 copy), running w2_rows.py instead.
# Invoked as:  hostless flock -s <quiet-lane.lock> locked_w2.sh <ledger> <row> <block> <attempts> <out>
# Environment (set by the caller): OWN36_LANES, OWN36_PYTHON, OWN36_DRIVER, OWN36_FIXTURE,
#   OWN36_WORKROOT, OWN36_SCRUB
set -uo pipefail
ledger=$1 row=$2 block=$3 attempts=$4 out=$5
here="$(cd "$(dirname "$0")" && pwd)"
work="$OWN36_WORKROOT/T2-$row-$block"
mkdir -p "$work"
acquired=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
la=$(cut -d' ' -f1-3 /proc/loadavg)
before=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); before=${before:-0}
CUA_SESSION_ATSPI=1 \
CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 DO_NOT_TRACK=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 OWN36_DRIVER=$OWN36_DRIVER OWN36_FIXTURE=$OWN36_FIXTURE OWN36_WORK=$work OWN36_SCRUB=$OWN36_SCRUB OWN36_PYTHON=$OWN36_PYTHON" \
  "$OWN36_LANES/cua-x11-session.sh" "$OWN36_PYTHON" "$here/w2_rows.py" \
  --row "$row" --block "$block" --attempts "$attempts" --out "$out" > "$work/session.log" 2>&1
rc=$?
after=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); after=${after:-0}
released=$(date -u +%Y-%m-%dT%H:%M:%S.%NZ)
printf '{"lock":"quiet-lane.lock","mode":"shared","topology":"T2","row":"%s","block":"%s","attempts_requested":"%s","attempts_recorded":%d,"acquired_utc":"%s","released_utc":"%s","loadavg_at_acquire":"%s","rc":%d}\n' \
  "$row" "$block" "$attempts" "$((after - before))" "$acquired" "$released" "$la" "$rc" >> "$ledger"
exit $rc
