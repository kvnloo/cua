#!/usr/bin/env bash
# run-pilot.sh <label> <rounds>: pilot of run_b08.py (plan pilot) under the SHARED quiet-lane lock
# (shared-locked.sh receipt), load rule disabled (--load-max 100). Excluded from every analysis; sets no gate.
# Same environment variables as run-chunk.sh. Invoke as: hostless bash run-pilot.sh ...
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LABEL="$1"; ROUNDS="$2"
LANES="${B08_LANES:?}"; WT="${B08_WT:?}"; LT="${B08_TMPDIR:?}"; DRV="${B08_DRIVER:?}"; SHA="${B08_DRIVER_SHA256:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$LT/logs"
export TMPDIR="$LT"
unset TYPESAFE_API_KEY CUA_SESSION_FORWARD_SECRETS
export CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1 B08_LOCK=shared B08_LOCK_LABEL=b08-$LABEL B08_HOSTLESS=1 B08_TMPDIR=$LT"
bash "$HERE/shared-locked.sh" "b08-$LABEL" timeout -k 15 600 bash "$HERE/session-retry.sh" "$LANES" "$WT" \
  run_b08.py --driver "$DRV" --driver-sha256 "$SHA" --out "$LT/pilot" --plan pilot --rounds "$ROUNDS" \
  --block pilot --attempt 1 --budget-s 450 --load-max 100 2>&1 | tee -a "$LT/logs/b08-$LABEL.log"
exit "${PIPESTATUS[0]}"
