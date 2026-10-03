#!/usr/bin/env bash
# RECERT-FIX a3 Part D: OWN-16W REAL rows on U'' / F'' (harness/own16w-w3, wave-3 copy).
# Adapted from harness/own16w-w3/run_batch.sh: each session holds the SHARED quiet-lane lock through
# qlock.sh (correctness rows, no timing claims) instead of quiet-timed; sessions, rows, rotations and
# oracles are the wave-3 ones. 0-3 s jitter before each session.
# usage (under hostless): own16w_a3.sh <out-dir> <phase x11|sw|all>
# Required env: A3_LANES, A3_WT (worktree holding the GTK3 fixture and the jev-use venv),
#   A3_DRIVER_U16, A3_DRIVER_F16, A3_ORACLE_PY (python with python-xlib), CUA_LANE_LOCKDIR
set -uo pipefail
OUT="$1"; PHASE="${2:-all}"
here="$(cd "$(dirname "$0")" && pwd)"
H16="$(dirname "$here")/own16w-w3"
LANES="$A3_LANES"; WT="$A3_WT"
mkdir -p "$OUT"
BASE_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
log() { echo "[$(date -u +%FT%TZ)] $* loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"; }
drv() { [ "$1" = U ] && echo "$A3_DRIVER_U16" || echo "$A3_DRIVER_F16"; }

session() {  # mode(SW|X11) bin(U|F) id rotation [extra harness args...]
  local mode="$1" bin="$2" id="$3" rot="$4"; shift 4
  local d="$OUT/$mode/$bin/$id"; mkdir -p "$d"
  local envmode script extra
  case "$mode" in SW) envmode=sway-wayland;; X11) envmode=x11;; esac
  if [ "$mode" = X11 ]; then script="$LANES/cua-x11-session.sh"; else script="$LANES/cua-sway-session.sh"; fi
  extra="CUA_SESSION_ATSPI=1 $BASE_ENV"
  [ "$mode" != X11 ] && extra="$extra WAYLAND_DEBUG=server"
  local jitter_ms=$((RANDOM % 3001))
  sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
  local cmd=(env CUA_SESSION_ATSPI=1 CUA_SWAY_TIMEOUT=900 CUA_SESSION_EXTRA_ENV="$extra"
             "$script" "$H16/run_in_session.sh" "$WT" "$(drv "$bin")" "$d/raw" "$d/work"
             --env-mode "$envmode" --mode truth --label "$mode-$bin-$id" --binary-tag "$bin" --rotation "$rot"
             --oracle-python "$A3_ORACLE_PY" --recorder "$H16/xrecord_capture.py" "$@")
  ( cd "$WT" && "$here/qlock.sh" shared "a3-own16w-$mode-$bin-$id" "$OUT/lock-ledger.jsonl" "${cmd[@]}" \
      > "$d/session.log" 2>&1 )
  log "$mode-$bin-$id rc=$? jitter_ms=$jitter_ms"
}

X11_ROWS="both,string_false,string_true"
log "batch start phase=$PHASE"
if [ "$PHASE" = all ] || [ "$PHASE" = x11 ]; then
  session X11 U T1 0 --rows "$X11_ROWS"; session X11 F T1 0 --rows "$X11_ROWS"
  session X11 F T2 3 --rows "$X11_ROWS"; session X11 U T2 3 --rows "$X11_ROWS"
fi
if [ "$PHASE" = all ] || [ "$PHASE" = sw ]; then
  session SW F T1 0
  session SW F T2 3
fi
log "batch done phase=$PHASE"
