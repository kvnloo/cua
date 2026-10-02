#!/usr/bin/env bash
# usage: run_batch.sh <lanes-dir> <worktree> <lane-driver> <main-driver> <tmp-root> <oracle-python>
# Pre-registered OWN-16 sessions, each in its own isolated X11 session, every session kept:
#   S1 measured (rotation 0) -> N1 negative (no AT-SPI bus) -> S2 measured (rotation 3) -> D1 smoke.
# Measured sessions take the quiet-lane lock themselves (SHARED, EXCLUSIVE for the warm block);
# N1 and D1 run under flock -s on the same lock.
set -uo pipefail
LANES="$1"; WT="$2"; LANE="$3"; MAIN="$4"; TMPR="$5"; OPY="$6"
LOCK="$TMPR/locks/quiet-lane.lock"; OUT="$TMPR/own16/runs"; mkdir -p "$OUT"
PKT="$WT/docs/experiments/own-16-modality-truth-2026-10-02"
SESSION="$LANES/cua-x11-session.sh"
measured() {  # name rotation
  local d="$OUT/$1"; mkdir -p "$d"
  ( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" "$SESSION" "$PKT/run_in_session.sh" \
      "$WT" "$LANE" "$d/raw" "$d/work" --mode measured --label "$1" --rotation "$2" --warm-rounds 20 \
      --oracle-rounds 3 --lock "$LOCK" --oracle-python "$OPY" --recorder "$PKT/xrecord_capture.py" > "$d/session.log" 2>&1 )
  echo "[$(date -u +%FT%TZ)] $1 rc=$? loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
}
echo "[$(date -u +%FT%TZ)] batch start"
measured S1 0
d="$OUT/N1"; mkdir -p "$d"
( cd "$WT" && env -u CUA_SESSION_ATSPI -u CUA_SESSION_EXTRA_ENV flock -s "$LOCK" "$SESSION" "$PKT/run_in_session.sh" \
    "$WT" "$LANE" "$d/raw" "$d/work" --mode negative --label N1 --warm-rounds 5 > "$d/session.log" 2>&1 )
echo "[$(date -u +%FT%TZ)] N1 rc=$? loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
measured S2 3
d="$OUT/D1"; mkdir -p "$d"
( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" flock -s "$LOCK" "$SESSION" "$PKT/run_in_session.sh" \
    "$WT" "$LANE" "$d/raw" "$d/work" --mode smoke --label D1 --main-driver "$MAIN" > "$d/session.log" 2>&1 )
echo "[$(date -u +%FT%TZ)] D1 rc=$? loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
echo "[$(date -u +%FT%TZ)] batch done"
