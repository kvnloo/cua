#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   hostless run_group.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> <tmp-root> <label-prefix> <group> <block> [block ...]
# Like run_all.sh, but ONE exclusive quiet-lane acquisition (bin/quiet-timed, receipt label
# r2-09-<prefix>-group-<group>) runs several blocks back to back, each in its own isolated X11 +
# private AT-SPI session; the group is sized to stay under 15 minutes. Receipts and the block list
# are appended to <runs-dir>/groups.jsonl. A session that fails before writing trials.jsonl is kept
# under its label and the block is re-run under <prefix>-<block>-rN (at most 2 re-runs) inside the
# same acquisition.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; TMPR="$6"; PREFIX="$7"; GROUP="$8"; shift 8
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
LANES="${R209_LANES:?set R209_LANES to the lanes dir (holds cua-x11-session.sh and bin/quiet-timed)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
export TMPDIR="$TMPR" WT DRV DSHA PLAN RUNS TMPR PREFIX LANES HERE GROUP
mkdir -p "$RUNS"
echo "[$(date -u +%FT%T.%3NZ)] group $GROUP blocks=$* requesting the exclusive quiet-lane lock"
"$LANES/bin/quiet-timed" "r2-09-$PREFIX-group-$GROUP" bash -c '
  printf "{\"group\":\"%s\",\"acquired\":\"%s\",\"blocks\":\"%s\"}\n" "$GROUP" "$(date -u +%FT%T.%3NZ)" "$*" >> "$RUNS/groups.jsonl"
  for b in "$@"; do
    for attempt in 0 1 2; do
      label="$PREFIX-$b"; n=0
      while [ -e "$RUNS/$label" ]; do n=$((n+1)); label="$PREFIX-$b-r$n"; done
      dir="$RUNS/$label"; mkdir -p "$dir"
      echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label loadavg=$(cut -d" " -f1-3 /proc/loadavg)"
      ( cd "$WT" && env CUA_SESSION_ATSPI=1 \
          "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
          "$LANES/cua-x11-session.sh" "$HERE/run_block.sh" "$WT" "$DRV" "$DSHA" "$PLAN" "$b" "$label" \
          "$dir/raw" "$TMPR/r209/$label" ) > "$dir/session.log" 2>&1
      rc=$?
      echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(grep -E "^done:" "$dir/session.log" | tail -1 | cut -c1-200)"
      [ -s "$dir/raw/trials.jsonl" ] && break
    done
  done
  printf "{\"group\":\"%s\",\"released\":\"%s\"}\n" "$GROUP" "$(date -u +%FT%T.%3NZ)" >> "$RUNS/groups.jsonl"
' _ "$@"
