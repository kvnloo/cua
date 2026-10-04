#!/usr/bin/env bash
# RECERT-FIX native campaign (new; adapted from campaign_fix02.sh): U' and F' blocks interleaved.
# Per block: hostless -> flock -s cargo-build.lock (taken first) -> flock -s quiet-lane.lock ->
# locked_block.sh (private X11 session, at most 10 attempts). A fresh Driver and a fresh fixture per
# block (run_block.py starts both).
# usage: campaign_recert.sh <raw-dir> <plan-file>
#   plan lines: <arm U|F> <topology> <row> <block> <attempts> [run_block flags...]
# Required environment: RECERT_DRIVER_U RECERT_DRIVER_F OWN36_LANES OWN36_LOCK OWN36_CARGO_LOCK
#                       OWN36_PYTHON OWN36_FIXTURE OWN36_WORKROOT OWN36_SCRUB [RECERT_GLOBAL_LEDGER]
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$raw"
while read -r arm topology row block attempts rest; do
  [ -z "${arm:-}" ] && continue
  case "$arm" in \#*) continue ;; esac
  case "$arm" in U) drv="$RECERT_DRIVER_U" ;; F) drv="$RECERT_DRIVER_F" ;; *) echo "bad arm $arm"; continue ;; esac
  # shellcheck disable=SC2206
  flags=(${rest:-})
  # A block that crashed before its first attempt (0 attempts recorded, e.g. the private Xvfb exited
  # before GTK initialised) is kept and re-run once under the id <block>R.
  for id in "$block" "${block}R"; do
    out="$raw/$arm/$topology/$row/b$id.jsonl"
    mkdir -p "$(dirname "$out")"
    echo "[$(date -u +%FT%TZ)] block $arm $topology $row $id $attempts ${flags[*]:-}"
    OWN36_DRIVER="$drv" OWN36_WORKROOT="$OWN36_WORKROOT/$arm" RECERT_CARGO_LOCK_MODE=shared \
      "$OWN36_LANES/bin/hostless" flock -s "$OWN36_CARGO_LOCK" flock -s "$OWN36_LOCK" \
      "$here/locked_block.sh" "$raw/lock-ledger.jsonl" "$topology" "$row" "$arm-$id" "$attempts" "$out" "${flags[@]}"
    rc=$?
    echo "  rc=$rc"
    recorded=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); recorded=${recorded:-0}
    [ "$recorded" -gt 0 ] && break
  done
done < "$plan"
