#!/usr/bin/env bash
# usage (host side, always under bin/hostless):
#   LANE_LOCK=<quiet-lane.lock> LANE_SESSION=<cua-x11-session.sh> LANE_TREES=<trees dir> \
#   [CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY] hostless live_block.sh <label> <locks.jsonl> <harness args...>
# Takes the quiet-lane lock SHARED for one block (<= 10 cells), records a lock receipt line, and runs
# the cell harness inside a private Xvfb session (cua-x11-session.sh).
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
LABEL="$1"; LEDGER="$2"; shift 2
HERE="$(cd "$(dirname "$0")" && pwd)"
req="$(date -u +%FT%T.%3NZ)"
exec 9>"$LANE_LOCK"
flock -s 9
acq="$(date -u +%FT%T.%3NZ)"
"$LANE_SESSION" bash "$HERE/in_session.sh" "$LANE_TREES/f/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/own78a_harness.py" "$@"
rc=$?
rel="$(date -u +%FT%T.%3NZ)"
printf '{"label":"%s","mode":"shared","requested":"%s","acquired":"%s","released":"%s","rc":%d}\n' "$LABEL" "$req" "$acq" "$rel" "$rc" >> "$LEDGER"
exit "$rc"
