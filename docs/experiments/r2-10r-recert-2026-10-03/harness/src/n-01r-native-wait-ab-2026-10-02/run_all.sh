#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless):
#   hostless run_all.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> <tmp-root> <label-prefix> [block ...]
# Runs each plan block in its own isolated X11 + private AT-SPI session.
#   exclusive blocks: under quiet-timed (EXCLUSIVE quiet-lane lock, receipt in the shared ledger),
#                     taken before the session (and so before any Driver MCP session) opens;
#   shared blocks (controls, <= 10 trials): under flock -s on the quiet-lane lock, receipts
#                     appended to <runs-dir>/lock-ledger-shared.jsonl.
# Every block is kept. A display collision or session failure keeps the failed cells and the
# block is re-run under a new label (<prefix>-<block>-rN) by calling this script again.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; TMPR="$6"; PREFIX="$7"; shift 7
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
# hostless (v2, 2026-10-02T05:06Z) strips the desktop variables and applies a Landlock scope but no
# longer masks the host runtime/X11 socket dirs; this lane nests hostless-strict (the v1 mount mask)
# inside it: hostless hostless-strict run_all.sh ...  Refuse if host desktop sockets are visible.
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_all.sh ...)" >&2; exit 95
fi
LANES="${N01R_LANES:?set N01R_LANES to the lanes dir (holds cua-x11-session.sh and bin/quiet-timed)}"
LOCK="$TMPR/locks/quiet-lane.lock"
HERE="$(cd "$(dirname "$0")" && pwd)"
export TMPDIR="$TMPR"
mkdir -p "$RUNS"
declare -A LOCKMODE
order=()
while read -r name mode; do LOCKMODE[$name]="$mode"; order+=("$name"); done < <(
  python3 -c 'import json,sys; [print(b["block"], b["lock"]) for b in json.load(open(sys.argv[1]))["blocks"]]' "$PLAN")
blocks=("$@")
[ ${#blocks[@]} -eq 0 ] && blocks=("${order[@]}")
for b in "${blocks[@]}"; do
  mode="${LOCKMODE[$b]:-}"
  [ -n "$mode" ] || { echo "unknown block $b" >&2; exit 2; }
  label="$PREFIX-$b"; n=0
  while [ -e "$RUNS/$label" ]; do n=$((n+1)); label="$PREFIX-$b-r$n"; done
  dir="$RUNS/$label"; mkdir -p "$dir"
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label lock=$mode loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  session=(env CUA_SESSION_ATSPI=1 "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1" "$LANES/cua-x11-session.sh"
           "$HERE/run_block.sh" "$WT" "$DRV" "$DSHA" "$PLAN" "$b" "$label" "$dir/raw" "$TMPR/n01r/$label")
  if [ "$mode" = exclusive ]; then
    ( cd "$WT" && "$LANES/bin/quiet-timed" "$label" "${session[@]}" ) > "$dir/session.log" 2>&1
    rc=$?
  else
    ( cd "$WT" && flock -s "$LOCK" bash -c '
        printf "{\"label\":\"%s\",\"mode\":\"shared\",\"acquired\":\"%s\",\"loadavg\":\"%s\"}\n" "$1" "$(date -u +%FT%T.%3NZ)" "$(cut -d" " -f1-3 /proc/loadavg)" >> "$2"
        shift 2; "$@"; rc=$?
        printf "{\"label\":\"%s\",\"mode\":\"shared\",\"released\":\"%s\",\"rc\":%d}\n" "'"$label"'" "$(date -u +%FT%T.%3NZ)" "$rc" >> "'"$RUNS"'/lock-ledger-shared.jsonl"
        exit $rc' _ "$label" "$RUNS/lock-ledger-shared.jsonl" "${session[@]}" ) > "$dir/session.log" 2>&1
    rc=$?
  fi
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(tail -1 "$dir/session.log" | cut -c1-160)"
done
