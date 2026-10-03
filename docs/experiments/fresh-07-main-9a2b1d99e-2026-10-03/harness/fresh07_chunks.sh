#!/usr/bin/env bash
# FRESH-07 Phase 2 chunk loop (on the host, ALWAYS through hostless; native rows also hostless-strict).
#   fresh07_chunks.sh <exclusive|shared> <atspi:0|1> <chunk-prefix> <runs-dir> <done-cmd> -- <in-session command...>
# Repeats chunks until <done-cmd> (evaluated by bash) exits 0. One chunk = one lock acquisition and one
# private X11 session (cua-x11-session.sh; telemetry off; DO_NOT_TRACK=1; R2_10_OUTER_HOSTLESS=1).
#   exclusive: wait (outside every lock) until the cargo-build lock is free, then
#              bin/quiet-timed fresh07-<chunk> flock -w 60 <cargo-build.lock> timeout -k 15 900 <session>
#              (EXCLUSIVE quiet-lane lock with its ledger receipt; no build can start inside the window).
#   shared:    flock -s on the quiet-lane lock, receipt lines in <runs>/lock-ledger-shared.jsonl and in the
#              shared quiet-lane ledger.
# In-session exit codes: 75 = the load rule ended the chunk (wait 90 s outside the locks), 76 = soft cap,
# 93/97 = the private display failed its probe (new session). Every chunk's session log is kept.
# Machine paths come from the environment: FRESH07_LANES, FRESH07_LOCKDIR.
set -uo pipefail
MODE="$1"; ATSPI="$2"; PREFIX="$3"; RUNS="$4"; DONE_CMD="$5"; shift 5
[ "$1" = "--" ] && shift
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${FRESH07_LANES:?}"; LOCKDIR="${FRESH07_LOCKDIR:?}"
LOCK="$LOCKDIR/quiet-lane.lock"; CARGO="$LOCKDIR/cargo-build.lock"; LEDGER="$LOCKDIR/quiet-lane-ledger.jsonl"
[ -e "$LOCK" ] || { echo "refusing: quiet-lane lock missing" >&2; exit 94; }
mkdir -p "$RUNS/chunks"
extra="R2_10_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
# non-timing rows (smoke, tools/list) only: forwarded into the session so r210r_session.sh skips the load rule
[ "${FRESH07_NO_LOAD_GATE:-0}" = 1 ] && extra="$extra FRESH07_NO_LOAD_GATE=1"
envs=(env -u TYPESAFE_API_KEY -u CUA_SESSION_FORWARD_SECRETS)
if [ "$ATSPI" = 1 ]; then envs+=(CUA_SESSION_ATSPI=1); extra="CUA_SESSION_ATSPI=1 $extra"; fi
envs+=("CUA_SESSION_EXTRA_ENV=$extra")
session=("${envs[@]}" "$LANES/cua-x11-session.sh" "$@")
la() { cut -d' ' -f1-3 /proc/loadavg; }
n=0; fails=0
until bash -c "$DONE_CMD"; do
  n=$((n + 1)); while [ -e "$RUNS/chunks/$PREFIX-c$(printf %02d $n).session.log" ]; do n=$((n + 1)); done
  chunk="$PREFIX-c$(printf %02d $n)"; slog="$RUNS/chunks/$chunk.session.log"
  if [ "$MODE" = exclusive ]; then
    until flock -n "$CARGO" true; do sleep 5; done   # cargo-lock check before acquiring the quiet lane
    echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk mode=exclusive loadavg=$(la)"
    "$LANES/bin/quiet-timed" "fresh07-$chunk" flock -w 60 "$CARGO" timeout -k 15 900 "${session[@]}" > "$slog" 2>&1
    rc=$?
  else
    echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk mode=shared loadavg=$(la)"
    exec 8>"$LOCK"; flock -s 8
    acq="$(date -u +%FT%T.%3NZ)"; la_acq="$(la)"
    "${session[@]}" > "$slog" 2>&1; rc=$?
    line=$(printf '{"lane":"FRESH-07","label":"fresh07-%s","mode":"shared","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}' \
      "$chunk" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la_acq")
    printf '%s\n' "$line" >> "$RUNS/lock-ledger-shared.jsonl"; printf '%s\n' "$line" >> "$LEDGER"
    flock -u 8; exec 8>&-
  fi
  echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk rc=$rc loadavg=$(la)"
  case "$rc" in
    0) fails=0 ;;
    75) fails=0; sleep 90 ;;
    76|93|97) fails=0; sleep 5 ;;
    *) fails=$((fails + 1)); echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk failed rc=$rc (kept; consecutive $fails)" >&2
       [ "$fails" -ge 4 ] && { echo "stopping after 4 consecutive failed chunks" >&2; exit 3; }
       sleep 30 ;;
  esac
done
echo "[$(date -u +%FT%T.%3NZ)] done: $PREFIX"
