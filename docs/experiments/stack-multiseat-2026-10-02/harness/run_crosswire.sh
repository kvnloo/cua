#!/usr/bin/env bash
# run_crosswire.sh <dir> <tag>   host side, under hostless: session B (target) then session A (attack), 1 seat each.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
D="$1"; TAG="$2"; H="$(cd "$(dirname "$0")" && pwd)"
SESSION="${MS_SESSION_SCRIPT:?MS_SESSION_SCRIPT (cua-sway-session.sh) not set}"
mkdir -p "$D"; [ -e "$D/A" ] && { echo "exists: $D" >&2; exit 2; }
EXTRA="MS_GTK3_MAIN=$MS_GTK3_MAIN MS_VENV_PY=$MS_VENV/bin/python CUA_DRIVER_BIN=$CUA_DRIVER_BIN"
run() { ( cd "$H/../../../.." && CUA_SWAY_SEATS=1 CUA_SWAY_OUTPUTS=1280x800 CUA_SESSION_ATSPI=1 CUA_SWAY_TIMEOUT=600 \
          CUA_SESSION_EXTRA_ENV="$EXTRA" exec "$SESSION" "$H/crosswire.sh" "$@" ); }
run target "$D" > "$D/B.session.log" 2>&1 &
BP=$!
for _ in $(seq 1 120); do [ -e "$D/B/ready" ] && break; sleep 0.5; done
[ -e "$D/B/ready" ] || { echo "target not ready" >&2; touch "$D/done"; wait $BP; exit 3; }
run attack "$D" "$TAG" > "$D/A.session.log" 2>&1
echo "attack rc=$?" > "$D/rc.txt"
touch "$D/done"; wait $BP; echo "target rc=$?" >> "$D/rc.txt"
cat "$D/A/attempts.jsonl"
