#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless; this lane nests hostless-strict):
#   TMPDIR=<tmp> hostless hostless-strict env OWN20G_LANES=<lanes> run_all.sh <worktree> \
#       <driver-U> <sha256-U> <driver-G> <sha256-G> <plan.json> <runs-dir> <tmp-root> <label-prefix> [block ...]
# Derived from the N-02 run_all.sh. Runs each plan block in its own isolated X11 + private
# AT-SPI session (telemetry off, DO_NOT_TRACK=1 inside the session).
#   exclusive blocks: under quiet-timed (EXCLUSIVE quiet-lane lock, receipt in the shared ledger),
#                     taken before the session (and so before any Driver MCP session) opens;
#   shared blocks (<= 20 trials): under flock -s on the quiet-lane lock; one receipt line per block
#                     appended to the global quiet-lane ledger (lane, label, mode "shared", pid,
#                     acquired, released, rc, loadavg_at_acquire).
# Every block is kept. A failed session keeps its cells and the block is re-run under a new label.
set -uo pipefail
WT="$1"; DRVU="$2"; SHAU="$3"; DRVG="$4"; SHAG="$5"; PLAN="$6"; RUNS="$7"; TMPR="$8"; PREFIX="$9"; shift 9
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_all.sh ...)" >&2; exit 95
fi
LANES="${OWN20G_LANES:?set OWN20G_LANES to the lanes dir (holds cua-x11-session.sh and bin/quiet-timed)}"
LOCKDIR="$TMPR/../locks"
LOCK="$LOCKDIR/quiet-lane.lock"; LEDGER="$LOCKDIR/quiet-lane-ledger.jsonl"
[ -e "$LOCK" ] || { echo "refusing: quiet-lane lock $LOCK missing" >&2; exit 94; }
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
  session=(env CUA_SESSION_ATSPI=1
           "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1"
           "$LANES/cua-x11-session.sh"
           "$HERE/run_block.sh" "$WT" "$DRVU" "$SHAU" "$DRVG" "$SHAG" "$PLAN" "$b" "$label" "$dir/raw" "$TMPR/runs-work/$label")
  if [ "$mode" = exclusive ]; then
    ( cd "$WT" && "$LANES/bin/quiet-timed" "$label" "${session[@]}" ) > "$dir/session.log" 2>&1
    rc=$?
  else
    ( cd "$WT" && flock -s "$LOCK" bash -c '
        label="$1"; ledger="$2"; shift 2
        acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d" " -f1-3 /proc/loadavg)"
        "$@"; rc=$?
        rel="$(date -u +%FT%T.%3NZ)"
        printf "{\"lane\":\"OWN-20G\",\"label\":\"%s\",\"mode\":\"shared\",\"pid\":%d,\"acquired\":\"%s\",\"released\":\"%s\",\"rc\":%d,\"loadavg_at_acquire\":\"%s\"}\n" \
          "$label" "$$" "$acq" "$rel" "$rc" "$la" >> "$ledger"
        exit $rc' _ "$label" "$LEDGER" "${session[@]}" ) > "$dir/session.log" 2>&1
    rc=$?
  fi
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(tail -1 "$dir/session.log" | cut -c1-160)"
done
