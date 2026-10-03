#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   run_chunk_f.sh <label> <exclusive|shared|none> <worktree> <python-script> [args...]
# R2-07e's run_chunk_e.sh with the R2-07f lock rules (no provider in this lane: the key is never forwarded).
# exclusive: check the cargo-build lock is free BEFORE acquiring anything (flock -n; busy -> exit 74, nothing
#            ran), then bin/quiet-timed r207f-<label> (EXCLUSIVE quiet-lane lock + receipt line in the
#            quiet-lane ledger), then INSIDE it flock -w 60 on the cargo-build lock (no Driver build can start
#            inside a measured window; not acquired -> exit 74), a 0-2.9 s start jitter and the private X11
#            session, everything capped at 900 s by `timeout`.
# shared:    flock -s on the quiet-lane lock (receipt appended to the quiet-lane ledger and the lane ledger),
#            jitter, then the private X11 session (pilot, controls, identity reads).
# none:      unit tests only (no lock; never a measured or reported number).
# Inside the session: R2-07d driver/probe_then.sh (xdpyinfo probe) -> the R2-07c harness/in_session.sh
# (unchanged; refuses outside a private session) -> the jev-use venv python <python-script>.
# Machine paths come from the environment, never from the packet: R2_07F_LANES (lanes dir),
# R2_07F_LOCKDIR (shared lock dir), R2_07F_LEDGER (lane ledger file).
set -uo pipefail
LABEL="$1"; MODE="$2"; WT="$3"; shift 3
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R2_07F_LANES:?}"; LOCKDIR="${R2_07F_LOCKDIR:?}"; LEDGER="${R2_07F_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
EXP="$HERE/../.."
PROBE="$EXP/r2-07d-quiet-timing-phase-l-2026-10-03/driver/probe_then.sh"
INSESSION="$EXP/r2-07c-toggle-modal-compiled-2026-10-03/harness/in_session.sh"
extra="R2_07C_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 R2_07F_LOCK=$MODE"
envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS "CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" timeout --signal=TERM --kill-after=30 900 "$LANES/cua-x11-session.sh" "$PROBE" "$INSESSION" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
jitter() { sleep "$((RANDOM % 3)).$((RANDOM % 10))"; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  if ! flock -n "$LOCKDIR/cargo-build.lock" true; then
    echo "[$(date -u +%FT%T.%3NZ)] cargo-build lock busy before acquiring; nothing ran" >&2
    printf '{"lane":"R2-07f","label":"r207f-%s","mode":"exclusive","cargo_busy_precheck":true,"rc":74,"utc":"%s"}\n' \
      "$LABEL" "$(date -u +%FT%T.%3NZ)" >> "$LEDGER"
    exit 74
  fi
  ( cd "$WT" && "$LANES/bin/quiet-timed" "r207f-$LABEL" \
      flock -w 60 -E 74 "$LOCKDIR/cargo-build.lock" \
      timeout --signal=TERM --kill-after=30 900 \
      bash -c 'sleep "$((RANDOM % 3)).$((RANDOM % 10))"; exec "$@"' jitter "${session[@]}" )
  rc=$?
  printf '{"lane":"R2-07f","label":"r207f-%s","mode":"exclusive","cargo_lock_inside_quiet":true,"released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
elif [ "$MODE" = shared ]; then
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  jitter
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"R2-07f","label":"r207f-%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
else
  ( cd "$WT" && "${session[@]}" ); rc=$?
  printf '{"lane":"R2-07f","label":"r207f-%s","mode":"none","released":"%s","rc":%d}\n' "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" >> "$LEDGER"
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
