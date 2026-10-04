#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   run_chunk.sh <label> <exclusive|shared> <worktree> <python-script> [args...]
# exclusive: flock on the cargo-build lock first (cargo lock before quiet lock), then bin/quiet-timed
#            <label> (EXCLUSIVE quiet-lane lock + receipt line in the loop ledger), then the private
#            X11 session. One acquisition per chunk; chunks are sized to stay under 25 minutes.
# shared:    flock -s on the quiet-lane lock (receipt appended to the loop ledger and the lane ledger),
#            no cargo lock, then the private X11 session.
# The provider key is never forwarded (provider cap for this lane is 0).
# Machine paths come from the environment, never from the packet: B05_LANES (lanes dir),
# B05_LOCKDIR (shared lock dir), B05_LEDGER (lane ledger file).
set -uo pipefail
LABEL="$1"; MODE="$2"; WT="$3"; shift 3
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${B05_LANES:?}"; LOCKDIR="${B05_LOCKDIR:?}"; LEDGER="${B05_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
extra="R2_10_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
session=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS "CUA_SESSION_EXTRA_ENV=$extra"
         "$LANES/cua-x11-session.sh" "$HERE/in_session.sh" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  ( cd "$WT" && flock "$LOCKDIR/cargo-build.lock" "$LANES/bin/quiet-timed" "$LABEL" "${session[@]}" )
  rc=$?
  printf '{"lane":"B-05","label":"%s","mode":"exclusive+cargo","released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
else
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"B-05","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
