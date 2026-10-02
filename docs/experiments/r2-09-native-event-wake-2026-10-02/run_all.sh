#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   hostless run_all.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> <tmp-root> <label-prefix> [block ...]
# Runs each plan block in its own isolated X11 + private AT-SPI session under bin/quiet-timed
# (EXCLUSIVE quiet-lane lock taken before the session opens; receipt in the shared ledger).
# A session that fails before writing trials.jsonl (e.g. the private Xvfb dies at start) is kept
# under its label and the block is re-run under <prefix>-<block>-rN (at most 2 re-runs).
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; TMPR="$6"; PREFIX="$7"; shift 7
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R209_LANES:?set R209_LANES to the lanes dir (holds cua-x11-session.sh and bin/quiet-timed)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export TMPDIR="$TMPR"
mkdir -p "$RUNS"
order=($(python3 -c 'import json,sys; [print(b["block"]) for b in json.load(open(sys.argv[1]))["blocks"]]' "$PLAN"))
blocks=("$@")
[ ${#blocks[@]} -eq 0 ] && blocks=("${order[@]}")
for b in "${blocks[@]}"; do
  for attempt in 0 1 2; do
    label="$PREFIX-$b"; n=0
    while [ -e "$RUNS/$label" ]; do n=$((n+1)); label="$PREFIX-$b-r$n"; done
    dir="$RUNS/$label"; mkdir -p "$dir"
    echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    ( cd "$WT" && "$LANES/bin/quiet-timed" "r2-09-$label" env CUA_SESSION_ATSPI=1 \
        "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
        "$LANES/cua-x11-session.sh" "$HERE/run_block.sh" "$WT" "$DRV" "$DSHA" "$PLAN" "$b" "$label" \
        "$dir/raw" "$TMPR/r209/$label" ) > "$dir/session.log" 2>&1
    rc=$?
    echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(grep -E '^done:' "$dir/session.log" | tail -1 | cut -c1-200)"
    [ -s "$dir/raw/trials.jsonl" ] && break
  done
done
