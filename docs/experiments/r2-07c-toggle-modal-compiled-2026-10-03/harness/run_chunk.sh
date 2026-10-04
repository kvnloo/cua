#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   run_chunk.sh <label> <exclusive|shared|none> <live:0|1> <worktree> <python-script> [args...]
# exclusive: bin/quiet-timed <label> (EXCLUSIVE quiet-lane lock + receipt in the loop ledger), then
#            the private X11 session.
# shared:    flock -s on the quiet-lane lock (receipt appended to the loop ledger and the lane
#            ledger), then the private X11 session (controls; at most 10 cells per acquisition).
# none:      unit tests / shakedown only (no lock; never a measured or reported number).
# live=1 forwards the provider key by NAME only (CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY).
# Machine paths come from the environment, never from the packet: R2_07C_LANES (lanes dir),
# R2_07C_LOCKDIR (shared lock dir), R2_07C_LEDGER (lane ledger file). Adapted from R2-10 run_chunk.sh
# (no cargo lock: this lane builds nothing).
set -uo pipefail
LABEL="$1"; MODE="$2"; LIVE="$3"; WT="$4"; shift 4
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R2_07C_LANES:?}"; LOCKDIR="${R2_07C_LOCKDIR:?}"; LEDGER="${R2_07C_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
extra="R2_07C_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
envs=(env)
if [ "$LIVE" = 1 ]; then envs+=(CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY); else envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS); fi
envs+=("CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" "$LANES/cua-x11-session.sh" "$HERE/in_session.sh" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE live=$LIVE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  ( cd "$WT" && "$LANES/bin/quiet-timed" "$LABEL" "${session[@]}" )
  rc=$?
  printf '{"lane":"R2-07c","label":"%s","mode":"exclusive","released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
elif [ "$MODE" = shared ]; then
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"R2-07c","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
else
  ( cd "$WT" && "${session[@]}" ); rc=$?
  printf '{"lane":"R2-07c","label":"%s","mode":"none","released":"%s","rc":%d}\n' "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" >> "$LEDGER"
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
