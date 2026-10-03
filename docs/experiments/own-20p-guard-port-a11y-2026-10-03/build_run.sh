#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   build_run.sh <lanes-dir> <locks-dir> <target-family> <worktree> <label> [<worktree> <label> ...]
# One cargo-build lock acquisition, then the quiet-lane lock SHARED (no CPU-heavy build inside an
# exclusive timing window; cargo first, the order every lane uses), then the lane kit's build-driver.sh
# for each (worktree, label) pair in turn (exact CI release build, copied to <lanes>/bin/cua-driver-<label>).
# One receipt per build in the quiet-lane ledger. The built Driver is never run here.
set -uo pipefail
LANES="$1"; LOCKS="$2"; FAM="$3"; shift 3
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
exec 7>"$LOCKS/cargo-build.lock"; flock -x 7
exec 8>"$LOCKS/quiet-lane.lock"; flock -s 8
worst=0
while [ $# -ge 2 ]; do
  WT="$1"; LABEL="$2"; shift 2
  acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d' ' -f1-3 /proc/loadavg)"
  echo "cargo lock held $acq label=$LABEL head=$(git -C "$WT" rev-parse HEAD) tracked_changes=$(git -C "$WT" status --porcelain --untracked-files=no | wc -l)"
  "$LANES/build-driver.sh" "$WT" "$LABEL" "$FAM"
  rc=$?; [ $rc -ne 0 ] && worst=$rc
  rel="$(date -u +%FT%T.%3NZ)"
  echo "build $LABEL finished $rel rc=$rc"
  printf '{"lane":"OWN-20P","label":"build-%s","mode":"shared+cargo","pid":%d,"acquired":"%s","released":"%s","rc":%d,"loadavg_at_acquire":"%s"}\n' \
    "$LABEL" "$$" "$acq" "$rel" "$rc" "$la" >> "$LOCKS/quiet-lane-ledger.jsonl"
done
exit $worst
