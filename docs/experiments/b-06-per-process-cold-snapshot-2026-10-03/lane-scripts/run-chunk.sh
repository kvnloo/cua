#!/usr/bin/env bash
# run-chunk.sh <label> <main|wn> <rounds> [block] [attempt]: one measured chunk = cargo-build lock FIRST,
# then one EXCLUSIVE quiet-lane acquisition (bin/quiet-timed writes the ledger receipt), a 600 s cap
# INSIDE the acquisition, the private Xvfb session, binary R'. Exit 75 from the runner = the load rule
# or the time budget ended the chunk early (both locks released; the caller re-runs the remaining rounds).
# Invoke as: hostless bash run-chunk.sh ...  Machine paths come from the environment, never the packet:
#   B06_LANES (lanes dir), B06_WT (worktree), B06_TMPDIR (lane temp), B06_DRIVER (binary), B06_LOCKDIR.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LABEL="$1"; PLAN="$2"; ROUNDS="$3"; BLOCK="${4:-m}"; ATT="${5:-1}"
LANES="${B06_LANES:?}"; WT="${B06_WT:?}"; LT="${B06_TMPDIR:?}"; DRV="${B06_DRIVER:?}"; LOCKDIR="${B06_LOCKDIR:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LT/logs"
export TMPDIR="$LT"
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1 B06_LOCK=exclusive B06_LOCK_LABEL=$LABEL B06_HOSTLESS=1 B06_TMPDIR=$LT"
la() { cut -d' ' -f1-3 /proc/loadavg; }
{
  echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL plan=$PLAN rounds=$ROUNDS block=$BLOCK attempt=$ATT loadavg=$(la) hostless=$CUA_HOSTLESS"
  ( cd "$WT" && flock "$LOCKDIR/cargo-build.lock" "$LANES/bin/quiet-timed" "$LABEL" timeout 600 \
      bash "$HERE/session-retry.sh" "$LANES" "$WT" run_b06.py --driver "$DRV" --out "$LT/$PLAN" --plan "$PLAN" \
      --rounds "$ROUNDS" --block "$BLOCK" --attempt "$ATT" --budget-s 480 )
  rc=$?
  echo "[$(date -u +%FT%T.%3NZ)] chunk $LABEL rc=$rc loadavg=$(la)"
  exit $rc
} 2>&1 | tee -a "$LT/logs/$LABEL.log"
exit "${PIPESTATUS[0]}"
