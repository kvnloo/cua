#!/usr/bin/env bash
# run-chunk.sh <label> <rounds> [block] [attempt] [plan]: one measured chunk of run_b09.py (plan main, or ctl for
# the SMOKE + N-W2 controls after the measured rounds). Derived from B-08's run-chunk.sh.
# Lock order (B-09): the caller (run_all.py) has checked that the cargo-build lock is free BEFORE this script runs;
# then one EXCLUSIVE quiet-lane acquisition (bin/quiet-timed b09r-<label>; b09-<label> in wave 7; writes the ledger receipt), then, INSIDE
# it, the cargo-build lock taken with `flock -w 60`. If the cargo lock is not acquired within 60 s the chunk exits
# 74 with nothing run, the quiet lock is released, and the caller retries later; no lock is ever waited on without
# a bound while the other is held. `timeout 900` caps everything inside the quiet acquisition (cargo wait +
# session + trials); the runner starts no round past its --budget-s 780.
# B-09R (wave 8): ledger labels are b09r-<label>; the command inside quiet-timed first closes fd 9 (the
# quiet-lane lock fd), so no process started inside the window (Xvfb, dbus, fixtures, Driver, Chrome) can inherit
# it and keep the lock after the window ends. quiet-timed itself holds the lock for the whole window.
# Exit 75 from the runner = the load rule or the time budget ended the chunk early (rounds not started are run
# in a later chunk). Then the private Xvfb session (session-retry.sh -> cua-x11-session.sh -> in-session.sh).
# Invoke as: hostless bash run-chunk.sh ...  Machine paths come from the environment, never the packet:
#   B09_LANES (lanes dir), B09_WT (worktree), B09_TMPDIR (lane temp), B09_DRIVER (binary),
#   B09_DRIVER_SHA256 (expected sha256), B09_LOCKDIR (lock dir).
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LABEL="$1"; ROUNDS="$2"; BLOCK="${3:-m}"; ATT="${4:-1}"; PLAN="${5:-main}"
LANES="${B09_LANES:?}"; WT="${B09_WT:?}"; LT="${B09_TMPDIR:?}"; DRV="${B09_DRIVER:?}"; SHA="${B09_DRIVER_SHA256:?}"
LOCKDIR="${B09_LOCKDIR:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LT/logs"
export TMPDIR="$LT"
unset TYPESAFE_API_KEY CUA_SESSION_FORWARD_SECRETS CUA_LANE_EXP_ROUTINE_POLL_MS CUA_LANE_EXP_PC_SLEEP_MS
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 B09_LOCK=exclusive B09_LOCK_LABEL=b09r-$LABEL B09_HOSTLESS=1 B09_TMPDIR=$LT"
la() { cut -d' ' -f1-3 /proc/loadavg; }
{
  echo "[$(date -u +%FT%T.%3NZ)] chunk b09r-$LABEL plan=$PLAN rounds=$ROUNDS block=$BLOCK attempt=$ATT loadavg=$(la) hostless=$CUA_HOSTLESS"
  ( cd "$WT" && "$LANES/bin/quiet-timed" "b09r-$LABEL" bash -c 'exec 9>&-; exec "$@"' b09r-close-lock-fd timeout -k 15 900 \
      flock -E 74 -w 60 "$LOCKDIR/cargo-build.lock" \
      bash "$HERE/session-retry.sh" "$LANES" "$WT" run_b09.py --driver "$DRV" --driver-sha256 "$SHA" \
      --out "$LT/main" --plan "$PLAN" --rounds "$ROUNDS" --block "$BLOCK" --attempt "$ATT" --budget-s 780 )
  rc=$?
  [ "$rc" = 74 ] && echo "[$(date -u +%FT%T.%3NZ)] chunk b09r-$LABEL cargo-build lock not acquired in 60 s: nothing ran; retry later"
  echo "[$(date -u +%FT%T.%3NZ)] chunk b09r-$LABEL rc=$rc loadavg=$(la)"
  exit $rc
} 2>&1 | tee -a "$LT/logs/b09r-$LABEL.log"
exit "${PIPESTATUS[0]}"
