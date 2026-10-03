#!/usr/bin/env bash
# usage (under hostless): run_batch.sh <lanes-dir> <worktree> <U-driver> <F-driver> <tmp-root> <oracle-python> [phase]
# Pre-registered OWN-16W sessions (PREREG.json "sessions"), each in its own private session and each
# under quiet-timed (EXCLUSIVE quiet-lane lock + ledger receipt; every session is far below 15 min).
# Adapted from OWN-16 run_batch.sh. phase: truth1 | negative | truth2 | timing | smoke | all (default).
set -uo pipefail
LANES="$1"; WT="$2"; U="$3"; F="$4"; TMPR="$5"; OPY="$6"; PHASE="${7:-all}"
OUT="$TMPR/runs"; mkdir -p "$OUT"
PKT="$WT/docs/experiments/own-16w-sway-modality-2026-10-02"
QT="$LANES/bin/quiet-timed"
BASE_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
log() { echo "[$(date -u +%FT%TZ)] $* loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"; }
drv() { [ "$1" = U ] && echo "$U" || echo "$F"; }

session() {  # mode(SW|SX|X11) bin(U|F) id kind(truth|negative|timing) rotation [extra harness args...]
  local mode="$1" bin="$2" id="$3" kind="$4" rot="$5"; shift 5
  local d="$OUT/$mode/$bin/$id"; mkdir -p "$d"
  local envmode script extra
  local -a E=(env -u CUA_SESSION_ATSPI)
  case "$mode" in SW) envmode=sway-wayland;; SX) envmode=sway-xwayland;; X11) envmode=x11;; esac
  if [ "$mode" = X11 ]; then script="$LANES/cua-x11-session.sh"; else script="$LANES/cua-sway-session.sh"; fi
  extra="$BASE_ENV"
  if [ "$kind" != negative ]; then E+=(CUA_SESSION_ATSPI=1); extra="CUA_SESSION_ATSPI=1 $extra"; fi
  if [ "$kind" = truth ] && [ "$mode" != X11 ]; then extra="$extra WAYLAND_DEBUG=server"; fi
  ( cd "$WT" && "${E[@]}" CUA_SWAY_TIMEOUT=900 CUA_SESSION_EXTRA_ENV="$extra" \
      "$QT" "own16w-$mode-$bin-$id" "$script" "$PKT/run_in_session.sh" "$WT" "$(drv "$bin")" "$d/raw" "$d/work" \
      --env-mode "$envmode" --mode "$kind" --label "$mode-$bin-$id" --binary-tag "$bin" --rotation "$rot" \
      --oracle-python "$OPY" --recorder "$PKT/xrecord_capture.py" "$@" > "$d/session.log" 2>&1 )
  log "$mode-$bin-$id rc=$?"
}

X11_ROWS="both,string_false,string_true"
log "batch start phase=$PHASE"
if [ "$PHASE" = all ] || [ "$PHASE" = truth1 ]; then
  session SW U T1 truth 0; session SW F T1 truth 0
  session SX U T1 truth 0; session SX F T1 truth 0
  session X11 U T1 truth 0 --rows "$X11_ROWS"; session X11 F T1 truth 0 --rows "$X11_ROWS"
fi
if [ "$PHASE" = all ] || [ "$PHASE" = negative ]; then
  session SW U N1 negative 0 --warm-rounds 5; session SX U N1 negative 0 --warm-rounds 5
fi
if [ "$PHASE" = all ] || [ "$PHASE" = truth2 ]; then
  session SW F T2 truth 3; session SW U T2 truth 3
  session SX F T2 truth 3; session SX U T2 truth 3
  session X11 F T2 truth 3 --rows "$X11_ROWS"; session X11 U T2 truth 3 --rows "$X11_ROWS"
fi
if [ "$PHASE" = all ] || [ "$PHASE" = timing ]; then
  session SW U B1 timing 0 --pairs 21; session SX U B1 timing 0 --pairs 21
  session SX U B2 timing 1 --pairs 21; session SW U B2 timing 1 --pairs 21
fi
if [ "$PHASE" = all ] || [ "$PHASE" = smoke ]; then
  d="$OUT/SW/D1"; mkdir -p "$d"
  ( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SWAY_TIMEOUT=900 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 $BASE_ENV" \
      "$QT" own16w-SW-D1 "$LANES/cua-sway-session.sh" "$PKT/run_in_session.sh" "$WT" "$U" "$d/raw" "$d/work" \
      --env-mode sway-wayland --mode smoke --label SW-D1 --binary-tag U --alt-driver "$F" > "$d/session.log" 2>&1 )
  log "SW-D1 rc=$?"
fi
log "batch done phase=$PHASE"
