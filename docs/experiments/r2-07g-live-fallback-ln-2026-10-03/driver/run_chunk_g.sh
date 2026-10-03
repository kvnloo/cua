#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   run_chunk_g.sh <label> <exclusive|shared|none> <live:0|1> <worktree> <python-script> [args...]
# R2-07e driver/run_chunk_e.sh with this lane's lock rules. Never wait on one lock while holding the other.
# exclusive: first a NON-BLOCKING check that cargo-build.lock is free (exit 74 if a build holds it: no lock
#            was acquired, nothing ran); then bin/quiet-timed <label> (EXCLUSIVE quiet-lane lock + receipt
#            in the loop ledger), then INSIDE it flock -w 60 on cargo-build.lock (no Driver build can start
#            inside a measured window; exit 74 if not free within 60 s -> quiet-timed releases the quiet lock
#            and the caller retries). Then a 0-2.9 s start jitter and the private X11 session, capped at
#            900 s by `timeout`.
# shared:    flock -s on the quiet-lane lock (receipt appended to the loop ledger and the lane ledger),
#            jitter, then the private X11 session (controls, pre-PREREG shakedowns; <= 10 cells).
# none:      unit tests only (no lock; never a measured or reported number).
# Inside the session: R2-07d driver/probe_then.sh (xdpyinfo probe) -> the R2-07c harness/in_session.sh
# (unchanged; refuses outside a private session) -> the jev-use venv python <python-script>.
# live=1 forwards the provider key by NAME only (CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY).
# CUA_DRIVER_RS_TELEMETRY_ENABLED=false is passed through CUA_SESSION_EXTRA_ENV (the R2-10 harness also
# sets "0" in the Driver's own environment; the Driver parses both as off).
# Machine paths come from the environment, never from the packet: R2_07G_LANES (lanes dir),
# R2_07G_LOCKDIR (shared lock dir), R2_07G_LEDGER (lane ledger file).
set -uo pipefail
LABEL="$1"; MODE="$2"; LIVE="$3"; WT="$4"; shift 4
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R2_07G_LANES:?}"; LOCKDIR="${R2_07G_LOCKDIR:?}"; LEDGER="${R2_07G_LEDGER:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
EXP="$HERE/../.."
PROBE="$EXP/r2-07d-quiet-timing-phase-l-2026-10-03/driver/probe_then.sh"
INSESSION="$EXP/r2-07c-toggle-modal-compiled-2026-10-03/harness/in_session.sh"
extra="R2_07C_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1"
if [ "$LIVE" = 1 ]; then envs=(env CUA_SESSION_FORWARD_SECRETS=TYPESAFE_API_KEY); else envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS); fi
envs+=("CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" timeout --signal=TERM --kill-after=30 900 "$LANES/cua-x11-session.sh" "$PROBE" "$INSESSION" "$WT" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
jitter() { sleep "$((RANDOM % 3)).$((RANDOM % 10))"; }
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL mode=$MODE live=$LIVE loadavg=$(la)"
if [ "$MODE" = exclusive ]; then
  if ! flock -n "$LOCKDIR/cargo-build.lock" true; then
    rc=74
    printf '{"lane":"R2-07g","label":"%s","mode":"exclusive","precheck":"cargo_lock_held","acquired":false,"at":"%s","rc":%d,"loadavg":"%s"}\n' \
      "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
    echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL cargo lock held before acquiring: rc=$rc"
    exit $rc
  fi
  ( cd "$WT" && "$LANES/bin/quiet-timed" "$LABEL" \
      flock -w 60 -E 74 "$LOCKDIR/cargo-build.lock" \
      bash -c 'sleep "$((RANDOM % 3)).$((RANDOM % 10))"; exec "$@"' jitter "${session[@]}" )
  rc=$?
  printf '{"lane":"R2-07g","label":"%s","mode":"exclusive","cargo_precheck":"free","cargo_lock_inside_quiet":true,"released":"%s","rc":%d,"loadavg_at_release":"%s"}\n' \
    "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" "$(la)" >> "$LEDGER"
elif [ "$MODE" = shared ]; then
  exec 8>"$LOCKDIR/quiet-lane.lock"
  flock -s 8
  acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
  jitter
  ( cd "$WT" && "${session[@]}" ); rc=$?
  line=$(printf '{"lane":"R2-07g","label":"%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
    "$LABEL" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
  printf '%s\n' "$line" >> "$LEDGER"; printf '%s\n' "$line" >> "$LOCKDIR/quiet-lane-ledger.jsonl"
  flock -u 8
else
  ( cd "$WT" && "${session[@]}" ); rc=$?
  printf '{"lane":"R2-07g","label":"%s","mode":"none","released":"%s","rc":%d}\n' "$LABEL" "$(date -u +%FT%T.%3NZ)" "$rc" >> "$LEDGER"
fi
echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
exit $rc
