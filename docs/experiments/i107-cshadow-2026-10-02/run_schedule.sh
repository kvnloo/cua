#!/usr/bin/env bash
# kvnloo/cua#107 lane CSHADOW measured schedule (PREREG_AMENDMENT_1 "schedule").
#   usage: run_schedule.sh <lanes-root> <out-dir> [block-name-regex]
# Run it from a plain shell; every block runs as
#   hostless quiet-timed i107-cshadow-<block> cua-x11-session.sh <python> run_cshadow.py ...
# so each block is one exclusive quiet-lane receipt inside its own private X11 session.
# A block whose run manifest already exists is skipped (resume after interruption);
# every trial ever run is kept.
set -uo pipefail
LANES="$1"; OUT="$2"; ONLY="${3:-.}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd "$HERE/../../.." && pwd)"
PY="$WT/libs/cua-driver/examples/jev-use/.venv/bin/python"
DRV="$LANES/bin/cua-driver-i107-cshadow-904b249c1"
REF="$LANES/bin/cua-driver-i107-092b065d5"
mkdir -p "$OUT"

block() {  # block <name> <run_cshadow args...>
  local name="$1"; shift
  [[ "$name" =~ $ONLY ]] || return 0
  if [ -f "$OUT/run-manifest-$name.json" ]; then echo "skip $name (manifest exists)"; return 0; fi
  echo "block $name start $(date -u +%FT%TZ)"
  ( cd "$HERE" && "$LANES/bin/hostless" "$LANES/bin/quiet-timed" "i107-cshadow-$name" \
      "$LANES/cua-x11-session.sh" "$PY" run_cshadow.py --driver "$DRV" --out "$OUT" --block "$name" "$@" ) \
      > "$OUT/block-$name.log" 2>&1
  echo "block $name rc=$? end $(date -u +%FT%TZ)"
}

block doff-0 --plan defaultoff --trials 10 --ref-driver "$REF"
for k in 0 1 2; do
  block ovh-q$k --plan overhead --condition W-quiet --pairs 10 --pair-offset $((k * 10))
  block ovh-c$k --plan overhead --condition W-churn --pairs 10 --pair-offset $((k * 10))
done
for k in 0 1; do
  block fid-q$k --plan fidelity --condition W-quiet --trials 15 --pair-offset $((k * 15))
  block fid-c$k --plan fidelity --condition W-churn --trials 15 --pair-offset $((k * 15))
done
for k in 0 1 2 3 4 5; do
  block idle-q$k --plan idle --condition W-idle-quiet --pairs 5 --pair-offset $((k * 5))
  block idle-c$k --plan idle --condition W-idle-churn --pairs 5 --pair-offset $((k * 5))
done
for k in 0 1 2 3 4; do
  block ctl-$k --plan controls --trials 1 --pair-offset $k
done
for k in 0 1; do
  block res-$k --plan resident --pairs 3 --pair-offset $((k * 3))
done
