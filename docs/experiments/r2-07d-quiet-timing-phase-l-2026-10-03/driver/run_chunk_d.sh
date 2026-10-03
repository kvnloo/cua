#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   run_chunk_d.sh <label> <exclusive|shared|none> <live:0|1> <worktree> <python-script> [args...]
# exclusive: flock on the cargo-build lock FIRST (no Driver build can start inside a measured
#            window), then bin/quiet-timed <label> (EXCLUSIVE quiet-lane lock + receipt in the loop
#            ledger), then a 0-2.9 s start jitter and the private X11 session. The whole session is
#            capped at 600 s by `timeout` (one acquisition <= 10 min).
# shared:    flock -s on the quiet-lane lock (receipt appended to the loop ledger and the lane
#            ledger), jitter, then the private X11 session (controls; <= 10 cells per acquisition).
# none:      unit tests only (no lock; never a measured or reported number).
# Inside the session: driver/probe_then.sh (xdpyinfo probe) -> the R2-07c harness/in_session.sh
# (unchanged; refuses outside a private session) -> the jev-use venv python <python-script>.
# live=1 forwards the provider key by NAME only (CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY).
# Machine paths come from the environment, never from the packet: R2_07D_LANES (lanes dir),
# R2_07D_LOCKDIR (shared lock dir), R2_07D_LEDGER (lane ledger file).
set -uo pipefail
LABEL="$1"; MODE="$2"; LIVE="$3"; WT="$4"; shift 4
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R2_07D_LANES:?}"; LOCKDIR="${R2_07D_LOCKDIR:?}"; LEDGER="${R2_07D_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
INSESSION="$HERE/../../r2-07c-toggle-modal-compiled-2026-10-03/harness/in_session.sh"
extra="R2_07C_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
envs=(env)
if [ "$LIVE" = 1 ]; then envs+=(CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY); else envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS); fi
envs+=("CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" timeout --signal=TERM --kill-after=30 600 "$LANES/cua-x11-session.sh" "$HERE/probe_then.sh" "$INSESSION" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
jitter() { sleep "$((RANDOM % 3)).$((RANDOM % 10))"; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE live=$LIVE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  ( cd "$WT" && flock "$LOCKDIR/cargo-build.lock" "$LANES/bin/quiet-timed" "$LABEL" \
      bash -c 'sleep "$((RANDOM % 3)).$((RANDOM % 10))"; exec "$@"' jitter "${session[@]}" )
  rc=$?
  printf '{"lane":"R2-07d","label":"%s","mode":"exclusive","cargo_lock":true,"released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
elif [ "$MODE" = shared ]; then
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  jitter
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"R2-07d","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
else
  ( cd "$WT" && "${session[@]}" ); rc=$?
  printf '{"lane":"R2-07d","label":"%s","mode":"none","released":"%s","rc":%d}\n' "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" >> "$LEDGER"
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
