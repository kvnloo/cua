#!/usr/bin/env bash
# FIX-02 native campaign: U and F blocks interleaved, one shared quiet-lane lock acquisition per block.
# usage: campaign_fix02.sh <raw-dir> <plan-file>
#   plan lines: <arm U|F> <topology> <row> <block> <attempts>
# Each line runs as: hostless flock -s quiet-lane.lock locked_block.sh ... (the OWN-36 lock wrapper,
# copied unchanged), with OWN36_DRIVER set to the arm's binary.
# Required environment: FIX02_DRIVER_U FIX02_DRIVER_F OWN36_LANES OWN36_LOCK OWN36_PYTHON OWN36_FIXTURE
#                       OWN36_WORKROOT OWN36_SCRUB
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$raw"
while read -r arm topology row block attempts; do
  [ -z "${arm:-}" ] && continue
  case "$arm" in \#*) continue ;; esac
  case "$arm" in U) drv="$FIX02_DRIVER_U" ;; F) drv="$FIX02_DRIVER_F" ;; *) echo "bad arm $arm"; continue ;; esac
  # A block that crashed before its first attempt (0 attempts recorded, e.g. the private Xvfb exited
  # before GTK initialised) is kept and re-run once under the id <block>R.
  for id in "$block" "${block}R"; do
    out="$raw/$arm/$topology/$row/b$id.jsonl"
    mkdir -p "$(dirname "$out")"
    echo "[$(date -u +%FT%TZ)] block $arm $topology $row $id $attempts"
    OWN36_DRIVER="$drv" OWN36_WORKROOT="$OWN36_WORKROOT/$arm" "$OWN36_LANES/bin/hostless" flock -s "$OWN36_LOCK" \
      "$here/locked_block.sh" "$raw/lock-ledger.jsonl" "$topology" "$row" "$arm-$id" "$attempts" "$out"
    rc=$?
    echo "  rc=$rc"
    recorded=$(grep -c '"kind": "attempt"' "$out" 2>/dev/null); recorded=${recorded:-0}
    [ "$recorded" -gt 0 ] && break
  done
done < "$plan"
