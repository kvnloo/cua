#!/usr/bin/env bash
# PREREG-AMENDMENT-1 replacement for run_batch.sh (which stays unchanged and unused in the measured run).
# usage (under bin/hostless): run_batch_qt.sh <lanes-dir> <plan-dir> <out-dir> <work-root> <driver> <wt-head> <wt-m0> [block-glob]
# Runs every <plan-dir>/<block-glob> (default block-*.json) in name order. Each block is ONE
# <lanes>/bin/quiet-timed phase (EXCLUSIVE quiet-lane lock; receipt line in the shared quiet-lane
# ledger, label own75r-<block>) instead of run_batch.sh's flock -s on the same lock file (a nested
# shared flock inside quiet-timed's exclusive one would deadlock). Inside the lock it writes the
# packet's own acquired/released receipts to <out>/lock-ledger.jsonl, records which session
# variables the trials actually saw, starts one private X11 session with a private AT-SPI bus and
# Driver telemetry disabled (same in both arms), and runs the pre-registered harness/real_block.py.
set -uo pipefail
LANES="$1"; PLANS="$2"; OUT="$3"; WORK="$4"; DRV="$5"; WTH="$6"; WTM="$7"; GLOB="${8:-block-*.json}"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under bin/hostless" >&2; exit 97; }
HERE="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="$WTH/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py"
SESSION_EXTRA="CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
mkdir -p "$OUT/session-env"
for plan in "$PLANS"/$GLOB; do
  block="$(basename "$plan" .json)"
  n="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$plan")"
  [ "$n" -le 10 ] || { echo "refusing: $block has $n trials (> 10 per lock acquisition)" >&2; exit 98; }
  [ ! -e "$OUT/blocks/$block" ] || { echo "refusing: $block already ran (every trial is kept; no reruns)" >&2; exit 99; }
  export BLOCK="$block" N="$n" PLAN="$plan" OUT LANES HERE DRV FIXTURE WORK WTH WTM SESSION_EXTRA
  echo "[$(date -u +%FT%TZ)] wait-lock $block loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  ( cd "$WTH" && "$LANES/bin/quiet-timed" "own75r-$block" bash -c '
      led() { printf "{\"block\": \"%s\", \"event\": \"%s\", \"utc\": \"%s\", \"loadavg\": \"%s\", \"lock\": \"quiet-lane.lock\", \"mode\": \"exclusive\", \"via\": \"bin/quiet-timed\", \"label\": \"own75r-%s\", \"trials\": %s%s}\n" \
        "$BLOCK" "$1" "$(date -u +%FT%T.%NZ)" "$(cut -d" " -f1-3 /proc/loadavg)" "$BLOCK" "$N" "$2" >> "$OUT/lock-ledger.jsonl"; }
      led acquired ""
      CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="$SESSION_EXTRA" "$LANES/cua-x11-session.sh" bash -c '"'"'
          printf "{\"block\": \"%s\", \"CUA_DRIVER_RS_TELEMETRY_ENABLED\": \"%s\", \"DO_NOT_TRACK\": \"%s\", \"CUA_SESSION_ATSPI\": \"%s\", \"DISPLAY_set\": %s, \"WAYLAND_DISPLAY_set\": %s, \"HYPRLAND_INSTANCE_SIGNATURE_set\": %s, \"AT_SPI_BUS_ADDRESS_set\": %s, \"TYPESAFE_API_KEY_set\": %s}\n" \
            "$1" "${CUA_DRIVER_RS_TELEMETRY_ENABLED:-}" "${DO_NOT_TRACK:-}" "${CUA_SESSION_ATSPI:-}" \
            "$([ -n "${DISPLAY:-}" ] && echo true || echo false)" "$([ -n "${WAYLAND_DISPLAY:-}" ] && echo true || echo false)" \
            "$([ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && echo true || echo false)" \
            "$([ -n "${AT_SPI_BUS_ADDRESS:-}" ] && echo true || echo false)" "$([ -n "${TYPESAFE_API_KEY:-}" ] && echo true || echo false)" \
            > "$2/session-env/$1.json"
          shift 2; exec "$@"'"'"' _ "$BLOCK" "$OUT" \
        "$HERE/real_block.py" --plan "$PLAN" --block "$BLOCK" --out "$OUT" --work "$WORK/$BLOCK" \
        --driver "$DRV" --fixture "$FIXTURE" --wt head="$WTH" --wt m0="$WTM"
      rc=$?
      led released ", \"rc\": $rc"
      exit $rc
    ' ) > "$OUT/session-$block.log" 2>&1
  qrc=$?
  # the session log names its private run dir; keep the packet free of local paths and the host name
  sed -i -e "s#$(dirname "$(dirname "$LANES")")#<mnt>#g" -e "s#/mnt/[A-Za-z0-9_.-]*#<mnt>#g" -e "s#$HOME#<home>#g" \
    -e "s#\b$(uname -n)\b#<host>#g" "$OUT/session-$block.log"
  echo "[$(date -u +%FT%TZ)] quiet-timed rc=$qrc $block"
  grep -E '^\{|exit rc' "$OUT/session-$block.log" | tail -n 12 || true
done
echo "[$(date -u +%FT%TZ)] batch done"
