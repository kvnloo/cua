#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless; native chunks through hostless hostless-strict):
#   run_chunk.sh <label> <exclusive|shared> <atspi:0|1> <live:0|1> <worktree> <python-script> [args...]
# exclusive: flock on the cargo-build lock for the whole chunk, then bin/quiet-timed <label>
#            (EXCLUSIVE quiet-lane lock + receipt in the loop ledger), then the private X11 session.
#            (R2-10R deviation: R2-10 took the quiet lock first; the loop now orders cargo first.)
# shared:    flock -s on the quiet-lane lock (receipt appended to the loop ledger and the lane
#            ledger), no cargo lock, then the private X11 session.
# live=1 forwards the provider key by NAME only (CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY).
# Machine paths come from the environment, never from the packet: R2_10_LANES (lanes dir),
# R2_10_LOCKDIR (shared lock dir), R2_10_LEDGER (lane ledger file).
set -uo pipefail
LABEL="$1"; MODE="$2"; ATSPI="$3"; LIVE="$4"; WT="$5"; shift 5
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R2_10_LANES:?}"; LOCKDIR="${R2_10_LOCKDIR:?}"; LEDGER="${R2_10_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
extra="R2_10_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1 ${R2_10_SESSION_EXTRA:-}"
envs=(env)
if [ "$LIVE" = 1 ]; then envs+=(CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY); else envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS); fi
if [ "$ATSPI" = 1 ]; then envs+=(CUA_SESSION_ATSPI=1); extra="CUA_SESSION_ATSPI=1 $extra"; fi
envs+=("CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" "$LANES/cua-x11-session.sh" "$HERE/in_session.sh" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE atspi=$ATSPI live=$LIVE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  # R2-10R: cargo-build lock FIRST, then the EXCLUSIVE quiet lock (loop lock order).
  ( cd "$WT" && flock "$LOCKDIR/cargo-build.lock" "$LANES/bin/quiet-timed" "$LABEL" "${session[@]}" )
  rc=$?
  printf '{"lane":"R2-10R","label":"%s","mode":"exclusive+cargo","released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
else
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"R2-10R","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
