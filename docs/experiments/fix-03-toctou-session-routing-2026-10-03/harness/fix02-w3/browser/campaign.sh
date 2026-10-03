#!/usr/bin/env bash
# FIX-02 browser campaign: one shared quiet-lane lock acquisition (locked.sh) and one private X11
# session per block of <= 10 cells.
# usage: campaign.sh <raw-dir> <plan-file>
#   plan lines: <block-id> <phase f3|f3ctl|f4> <arm U|F> <code|-> <start-rep> <reps>
# Required environment: WT FIX02_DRIVER_U FIX02_DRIVER_F CUA_LANE_LOCKDIR TMPDIR OWN36_LANES (lanes root)
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
lanes="${OWN36_LANES:?set OWN36_LANES to the lanes root}"
mkdir -p "$raw"
while read -r block phase arm code start reps; do
  [ -z "${block:-}" ] && continue
  case "$block" in \#*) continue ;; esac
  case "$arm" in U) drv="$FIX02_DRIVER_U" ;; F) drv="$FIX02_DRIVER_F" ;; *) echo "bad arm $arm"; continue ;; esac
  extra=()
  [ "$code" != "-" ] && extra=(--code "$code")
  # A block that produced no cell (session or validity failure before the first cell) is kept and
  # re-run once under the id <block>R.
  for id in "$block" "${block}R"; do
    out="$raw/$id-$phase-$arm"
    [ "$code" != "-" ] && out="$out-$code"
    echo "[$(date -u +%FT%TZ)] block $id $phase $arm $code reps $start..$((start + reps - 1))"
    "$lanes/bin/hostless" env CUA_LANE_LOCKDIR="$CUA_LANE_LOCKDIR" \
      "$here/locked.sh" shared "fix02-$id-$phase-$arm-$code" "$raw/lock-ledger.jsonl" \
      env CUA_SESSION_EXTRA_ENV="FIX02_OUTER_HOSTLESS=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
      "$lanes/cua-x11-session.sh" "$here/run_block.sh" "$WT" --phase "$phase" --arm "$arm" --driver "$drv" \
      --out "$out" --start-rep "$start" --reps "$reps" "${extra[@]}" > "$out.session.log" 2>&1
    echo "  rc=$?"
    [ -s "$out/cells.jsonl" ] && break
  done
done < "$plan"
