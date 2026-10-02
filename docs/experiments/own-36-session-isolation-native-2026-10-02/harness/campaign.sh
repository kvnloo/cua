#!/usr/bin/env bash
# Run a list of OWN-36 blocks, one shared quiet-lane lock acquisition per block.
# usage: campaign.sh <raw-dir> <plan-file>
#   plan-file lines: <topology> <row> <block> <attempts> [--forged]
# Each line runs as: hostless flock -s quiet-lane.lock locked_block.sh ...
# Required environment: OWN36_LANES OWN36_LOCK OWN36_PYTHON OWN36_DRIVER OWN36_FIXTURE OWN36_WORKROOT OWN36_SCRUB
set -uo pipefail
raw=$1 plan=$2
here="$(cd "$(dirname "$0")" && pwd)"
lock="$OWN36_LOCK"
mkdir -p "$raw"
while read -r topology row block attempts forged; do
  [ -z "${topology:-}" ] && continue
  case "$topology" in \#*) continue ;; esac
  out="$raw/$topology/$row/b$block.jsonl"
  mkdir -p "$(dirname "$out")"
  echo "[$(date -u +%FT%TZ)] block $topology $row $block $attempts ${forged:-}"
  "$OWN36_LANES/bin/hostless" flock -s "$lock" \
    "$here/locked_block.sh" "$raw/lock-ledger.jsonl" "$topology" "$row" "$block" "$attempts" "$out" ${forged:-}
  echo "  rc=$?"
done < "$plan"
