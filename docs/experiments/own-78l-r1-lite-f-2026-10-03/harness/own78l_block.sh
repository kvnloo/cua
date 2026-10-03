#!/usr/bin/env bash
# usage (host side, always under bin/hostless):
#   LANE_LOCKDIR=<locks dir> LANE_SESSION=<cua-x11-session.sh> LANE_TREES=<trees dir> \
#   [CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY] hostless own78l_block.sh <label> <locks.jsonl> <harness args...>
# Takes the quiet-lane lock SHARED for exactly one cell, runs OWN-78L's harness inside a fresh private
# Xvfb session (cua-x11-session.sh, Driver telemetry off) through OWN-78A's in_session.sh (jitter +
# xdpyinfo probe), caps the hold at 295 s, and appends one receipt line to the packet's locks.jsonl
# and one to the machine-wide quiet-lane ledger.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
LABEL="$1"; LEDGER="$2"; shift 2
HERE="$(cd "$(dirname "$0")" && pwd)"
A_HARNESS="$HERE/../../own-78a-abstain-isolation-4394-2026-10-03/harness"
req="$(date -u +%FT%T.%3NZ)"
exec 9>"$LANE_LOCKDIR/quiet-lane.lock"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"; t0=$(date +%s%N); la="$(cut -d' ' -f1-3 /proc/loadavg)"
CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false" timeout -s TERM -k 5 295 \
  "$LANE_SESSION" bash "$A_HARNESS/in_session.sh" "$LANE_TREES/f/libs/cua-driver/examples/jev-use/.venv/bin/python" \
  "$HERE/own78l_harness.py" "$@" 9>&-
rc=$?
rel="$(date -u +%FT%T.%3NZ)"; held=$(( ($(date +%s%N)-t0)/1000000 ))
printf '{"label":"%s","mode":"shared","requested":"%s","acquired":"%s","released":"%s","held_ms":%d,"rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$LABEL" "$req" "$acq" "$rel" "$held" "$rc" "$la" >> "$LEDGER"
printf '{"lane":"OWN-78L","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
  "$LABEL" "$$" "$acq" "$rel" "$rc" "$la" >> "$LANE_LOCKDIR/quiet-lane-ledger.jsonl"
exec 9>&-
exit "$rc"
