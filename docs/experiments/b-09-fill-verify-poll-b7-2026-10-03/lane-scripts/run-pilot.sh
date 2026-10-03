#!/usr/bin/env bash
# run-pilot.sh <label> <rounds>: pilot of run_b09.py (plan pilot, <= 12 trials) under the SHARED quiet-lane lock
# (shared-locked.sh receipt), load rule disabled (--load-max 100). Excluded from every analysis; sets no gate.
# Same environment variables as run-chunk.sh. Invoke as: hostless bash run-pilot.sh ...
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LABEL="$1"; ROUNDS="$2"
LANES="${B09_LANES:?}"; WT="${B09_WT:?}"; LT="${B09_TMPDIR:?}"; DRV="${B09_DRIVER:?}"; SHA="${B09_DRIVER_SHA256:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LT/logs"
export TMPDIR="$LT"
unset TYPESAFE_API_KEY CUA_SESSION_FORWARD_SECRETS CUA_LANE_EXP_ROUTINE_POLL_MS CUA_LANE_EXP_PC_SLEEP_MS
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 B09_LOCK=shared B09_LOCK_LABEL=b09-$LABEL B09_HOSTLESS=1 B09_TMPDIR=$LT"
bash "$HERE/shared-locked.sh" "b09-$LABEL" timeout -k 15 900 bash "$HERE/session-retry.sh" "$LANES" "$WT" \
  run_b09.py --driver "$DRV" --driver-sha256 "$SHA" --out "$LT/pilot" --plan pilot --rounds "$ROUNDS" \
  --block pilot --attempt 1 --budget-s 780 --load-max 100 2>&1 | tee -a "$LT/logs/b09-$LABEL.log"
exit "${PIPESTATUS[0]}"
