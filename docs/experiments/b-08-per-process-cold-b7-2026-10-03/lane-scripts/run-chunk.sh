#!/usr/bin/env bash
# run-chunk.sh <label> <rounds> [block] [attempt]: one measured chunk of run_b08.py (plan main).
# Lock order (B-08): one EXCLUSIVE quiet-lane acquisition first (bin/quiet-timed b08-<label> writes the ledger
# receipt), then, INSIDE it, the cargo-build lock tried with `flock -w 60`. If the cargo lock is not acquired
# within 60 s the chunk exits 74 with nothing run, the quiet lock is released, and the caller retries later;
# no lock is ever waited on without a bound while the other is held. `timeout 600` caps everything inside the
# quiet acquisition (cargo wait + session + trials); the runner starts no round past its --budget-s 450.
# Exit 75 from the runner = the load rule or the time budget ended the chunk early (rounds not started are run
# in a later chunk). Then the private Xvfb session (session-retry.sh -> cua-x11-session.sh -> in-session.sh).
# Invoke as: hostless bash run-chunk.sh ...  Machine paths come from the environment, never the packet:
#   B08_LANES (lanes dir), B08_WT (worktree), B08_TMPDIR (lane temp), B08_DRIVER (binary),
#   B08_DRIVER_SHA256 (expected sha256), B08_LOCKDIR (lock dir).
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LABEL="$1"; ROUNDS="$2"; BLOCK="${3:-m}"; ATT="${4:-1}"
LANES="${B08_LANES:?}"; WT="${B08_WT:?}"; LT="${B08_TMPDIR:?}"; DRV="${B08_DRIVER:?}"; SHA="${B08_DRIVER_SHA256:?}"
LOCKDIR="${B08_LOCKDIR:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LT/logs"
export TMPDIR="$LT"
unset TYPESAFE_API_KEY CUA_SESSION_FORWARD_SECRETS
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 B08_LOCK=exclusive B08_LOCK_LABEL=b08-$LABEL B08_HOSTLESS=1 B08_TMPDIR=$LT"
la() { cut -d' ' -f1-3 /proc/loadavg; }
{
  echo "[$(date -u +%FT%T.%3NZ)] chunk b08-$LABEL plan=main rounds=$ROUNDS block=$BLOCK attempt=$ATT loadavg=$(la) hostless=$CUA_HOSTLESS"
  ( cd "$WT" && "$LANES/bin/quiet-timed" "b08-$LABEL" timeout -k 15 600 \
      flock -E 74 -w 60 "$LOCKDIR/cargo-build.lock" \
      bash "$HERE/session-retry.sh" "$LANES" "$WT" run_b08.py --driver "$DRV" --driver-sha256 "$SHA" \
      --out "$LT/main" --plan main --rounds "$ROUNDS" --block "$BLOCK" --attempt "$ATT" --budget-s 450 )
  rc=$?
  [ "$rc" = 74 ] && echo "[$(date -u +%FT%T.%3NZ)] chunk b08-$LABEL cargo-build lock not acquired in 60 s: nothing ran; retry later"
  echo "[$(date -u +%FT%T.%3NZ)] chunk b08-$LABEL rc=$rc loadavg=$(la)"
  exit $rc
} 2>&1 | tee -a "$LT/logs/b08-$LABEL.log"
exit "${PIPESTATUS[0]}"
