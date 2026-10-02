#!/usr/bin/env bash
# Host-side driver for the negative chunks (N1-N3 x 2 chunks of 10) and the N2 valid-value control.
# usage: run_negatives.sh <lanes-root> <worktree> <driver-bin> <artifact-dir> [<quiet-lane-lock>]
# Each chunk takes the quiet-lane lock SHARED (<= 10 trials per acquisition) and runs in its own
# private isolated X11 session via cua-x11-session.sh. Writes a lock receipt per chunk.
set -uo pipefail
L="$1"; WT="$2"; DRV="$3"; A="$4"
LOCK="${5:-$L/../../cua-lane-tmp/locks/quiet-lane.lock}"   # <lanes>/../../cua-lane-tmp = the lane temp root
run_chunk() {
  local name="$1"; shift
  local info="$A/$name.lockinfo"
  echo "mode=shared" > "$info"
  echo "lock_wait_start $(date -u +%FT%TZ)" >> "$info"
  flock -s "$LOCK" bash -c '
    info="$1"; shift; log="$1"; shift
    echo "lock_acquired $(date -u +%FT%TZ)" >> "$info"
    "$@" > "$log" 2>&1
    echo "rc=$?" >> "$info"
    echo "lock_released $(date -u +%FT%TZ)" >> "$info"' _ "$info" "$A/$name.log" \
    "$L/cua-x11-session.sh" "$WT/docs/experiments/r2-08-2026-10-02/run_in_session.sh" "$WT" "$DRV" "$@"
  echo "$name: $(tr '\n' ' ' < "$info")"
}
cd "$WT" || exit 1
for v in n1 n2 n3; do
  for c in 0 1; do
    run_chunk "neg-$v-c$c" "$A/neg/$v-c$c" --phase neg --variant "$v" --chunk "$c"
  done
done
run_chunk "n2ctl" "$A/n2ctl/run1" --phase n2ctl
