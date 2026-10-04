#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless; this lane nests hostless-strict, the v1 mount mask):
#   TMPDIR=<tmp> hostless hostless-strict env N03_LANES=<lanes> N03_LOCKDIR=<lockdir> \
#       run_all.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> <tmp-root> <label-prefix> [block ...]
# Derived from the N-02 run_all.sh. Runs each plan block in its own isolated X11 + private AT-SPI
# session (telemetry off, DO_NOT_TRACK=1 inside the session).
#   exclusive blocks: the cargo-build lock is taken FIRST (no Driver build can run during the block),
#                     then bin/quiet-timed (EXCLUSIVE quiet-lane lock, receipt in the shared ledger),
#                     both before the session (and so before any Driver MCP session) opens;
#   shared blocks (controls/pilot/smoke, <= 20 trials): flock -s on the quiet-lane lock; receipts are
#                     appended to <runs-dir>/lock-ledger-shared.jsonl and to the shared quiet-lane ledger.
# Every block is kept. A failed session keeps its cells and the block is re-run under a new label.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; TMPR="$6"; PREFIX="$7"; shift 7
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_all.sh ...)" >&2; exit 95
fi
LANES="${N03_LANES:?set N03_LANES to the lanes dir (holds cua-x11-session.sh and bin/quiet-timed)}"
LOCKDIR="${N03_LOCKDIR:?set N03_LOCKDIR to the shared lock dir}"
LOCK="$LOCKDIR/quiet-lane.lock"; CARGO_LOCK="$LOCKDIR/cargo-build.lock"
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
           "$HERE/run_block.sh" "$WT" "$DRV" "$DSHA" "$PLAN" "$b" "$label" "$dir/raw" "$TMPR/work/$label")
  if [ "$mode" = exclusive ]; then
    ( cd "$WT" && flock "$CARGO_LOCK" "$LANES/bin/quiet-timed" "$label" "${session[@]}" ) > "$dir/session.log" 2>&1
    rc=$?
  else
    ( cd "$WT" && flock -s "$LOCK" bash -c '
        acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d" " -f1-3 /proc/loadavg)"
        label="$1"; lane_ledger="$2"; global_ledger="$3"; shift 3
        "$@"; rc=$?
        line=$(printf "{\"lane\":\"N-03\",\"label\":\"%s\",\"mode\":\"shared\",\"pid\":%d,\"acquired\":\"%s\",\"released\":\"%s\",\"rc\":%d,\"loadavg_at_acquire\":\"%s\"}" \
          "$label" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la")
        printf "%s\n" "$line" >> "$lane_ledger"; printf "%s\n" "$line" >> "$global_ledger"
        exit $rc' _ "$label" "$RUNS/lock-ledger-shared.jsonl" "$LOCKDIR/quiet-lane-ledger.jsonl" "${session[@]}" ) \
      > "$dir/session.log" 2>&1
    rc=$?
  fi
  echo "[$(date -u +%FT%T.%3NZ)] block $b label=$label rc=$rc $(tail -1 "$dir/session.log" | cut -c1-160)"
done
