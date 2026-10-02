#!/usr/bin/env bash
# usage (under bin/hostless): run_batch.sh <lanes-dir> <plan-dir> <out-dir> <tmp-root> <driver> <wt-head> <wt-m0>
# Runs every <plan-dir>/block-*.json in name order. Each block takes the quiet-lane lock SHARED
# (flock -s, <= 10 trials per acquisition), starts its own private X11 session with a private
# AT-SPI bus, runs harness/real_block.py, and writes acquire/release receipts to <out>/lock-ledger.jsonl.
set -uo pipefail
LANES="$1"; PLANS="$2"; OUT="$3"; TMPR="$4"; DRV="$5"; WTH="$6"; WTM="$7"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under bin/hostless" >&2; exit 97; }
HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK="$TMPR/locks/quiet-lane.lock"
FIXTURE="$WTH/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
mkdir -p "$OUT"
for plan in "$PLANS"/block-*.json; do
  block="$(basename "$plan" .json)"
  n="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$plan")"
  [ "$n" -le 10 ] || { echo "refusing: $block has $n trials (> 10 per lock acquisition)" >&2; exit 98; }
  export BLOCK="$block" N="$n" PLAN="$plan" OUT LANES HERE DRV FIXTURE TMPR WTH WTM
  echo "[$(date -u +%FT%TZ)] wait-lock $block loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  ( cd "$WTH" && flock -s "$LOCK" bash -c '
      led() { printf "{\"block\": \"%s\", \"event\": \"%s\", \"utc\": \"%s\", \"loadavg\": \"%s\", \"lock\": \"quiet-lane.lock\", \"mode\": \"shared\", \"trials\": %s%s}\n" \
        "$BLOCK" "$1" "$(date -u +%FT%T.%NZ)" "$(cut -d" " -f1-3 /proc/loadavg)" "$N" "$2" >> "$OUT/lock-ledger.jsonl"; }
      led acquired ""
      CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1" "$LANES/cua-x11-session.sh" \
        "$HERE/real_block.py" --plan "$PLAN" --block "$BLOCK" --out "$OUT" --work "$TMPR/own-75/work/$BLOCK" \
        --driver "$DRV" --fixture "$FIXTURE" --wt head="$WTH" --wt m0="$WTM"
      rc=$?
      led released ", \"rc\": $rc"
    ' ) > "$OUT/session-$block.log" 2>&1
  tail -n 12 "$OUT/session-$block.log" | grep -E '^\{|exit rc' || true
done
echo "[$(date -u +%FT%TZ)] batch done"
