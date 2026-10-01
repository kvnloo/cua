#!/usr/bin/env bash
# usage: run_batch.sh <lanes-dir> <worktree> <main-driver> <phase-driver> <tmp-root> [rounds]
# Runs the pre-registered 8 sessions (M,P,P,M,P,M,M,P), each in its own isolated X11 + private
# AT-SPI session and each under the shared quiet-lane timing lock. Every session is kept.
set -uo pipefail
LANES="$1"; WT="$2"; MAIN="$3"; PHASE="$4"; TMPR="$5"; ROUNDS="${6:-10}"
LOCK="$TMPR/locks/quiet-lane.lock"
OUT="$TMPR/r2-04/runs"; mkdir -p "$OUT"
ORDER=(M P P M P M M P)
for i in "${!ORDER[@]}"; do
  arm="${ORDER[$i]}"; name="s$((i+1))-$arm"; dir="$OUT/$name"; mkdir -p "$dir"
  if [ "$arm" = M ]; then bin="$MAIN"; extra=(); else bin="$PHASE"; extra=(--phase-log "$dir/work/phase.jsonl"); fi
  echo "[$(date -u +%FT%TZ)] wait-lock $name loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  ( cd "$WT" && flock "$LOCK" bash -c '
      echo "[$(date -u +%FT%TZ)] start '"$name"' loadavg=$(cut -d" " -f1-3 /proc/loadavg)"
      CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" "$@"
      rc=$?
      echo "[$(date -u +%FT%TZ)] end '"$name"' rc=$rc loadavg=$(cut -d" " -f1-3 /proc/loadavg)"
    ' _ "$LANES/cua-x11-session.sh" "$WT/docs/experiments/r2-04-2026-10-01/run_in_session.sh" \
        "$WT" "$bin" "$dir/raw" "$dir/work" --arm "$arm" --rounds "$ROUNDS" "${extra[@]}" \
      > "$dir/session.log" 2>&1 )
  grep -E '^\[20' "$dir/session.log" | grep -E 'start|end' || true
done
echo "[$(date -u +%FT%TZ)] batch done"
