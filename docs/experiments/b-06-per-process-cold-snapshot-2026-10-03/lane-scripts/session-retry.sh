#!/usr/bin/env bash
# session-retry.sh <lanes-dir> <worktree> <in-session args...>: start the private Xvfb session after a
# 0-3 s random start jitter; when in-session.sh reports the display unreachable (rc 97, nothing ran),
# log a display-collision retry and start a new session (at most 3 attempts). CUA_SESSION_EXTRA_ENV is
# taken from the caller.
set -uo pipefail
LANES="$1"; WT="$2"; shift 2
HERE="$(cd "$(dirname "$0")" && pwd)"
rc=97
for attempt in 1 2 3; do
  j=$(( RANDOM % 3001 ))
  sleep "$(( j / 1000 )).$(printf '%03d' $(( j % 1000 )))"
  echo "[b06] session_attempt=$attempt jitter_ms=$j utc=$(date -u +%FT%T.%3NZ)" >&2
  "$LANES/cua-x11-session.sh" bash "$HERE/in-session.sh" "$WT" "$@"; rc=$?
  [ "$rc" = 97 ] || break
  echo "[b06] display_collision_retry attempt=$attempt rc=97 utc=$(date -u +%FT%T.%3NZ)" >&2
done
exit "$rc"
