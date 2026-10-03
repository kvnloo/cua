#!/usr/bin/env bash
# usage (on the host, ALWAYS through hostless + hostless-strict):
#   TMPDIR=<tmp> hostless hostless-strict env N04_LANES=<lanes> N04_LOCKDIR=<lockdir> \
#     run_chunks.sh <exclusive|shared> <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> \
#                   <tmp-root> <prefix> <max-wall-s> [--no-load-gate] <block>...
# Derived from the N-03 run_all.sh. Runs the given single-round blocks as CHUNKS. Each chunk is one
# lock acquisition and one isolated X11 + private AT-SPI session (telemetry off, DO_NOT_TRACK=1,
# TMPDIR in the lane tmp):
#   exclusive: the cargo-build lock is taken FIRST, then bin/quiet-timed <chunk> (EXCLUSIVE quiet-lane
#              lock, receipt line in the shared ledger); inside it a hard cap `timeout 600` (10 min per
#              acquisition) around the session; the harness itself stops starting rounds after 420 s;
#   shared:    flock -s on the quiet-lane lock with receipt lines in <runs>/lock-ledger-shared.jsonl and
#              in the shared ledger.
# Harness exit 75 = the load rule ended the chunk (1-min loadavg stayed > 4.0 for 60 s): wait 90 s
# OUTSIDE the locks and resume. 76 = the soft cap ended the chunk: resume. 93 = the session failed its
# xdpyinfo probe: resume in a fresh session. Every chunk's session log is kept in <runs>/chunks/.
set -uo pipefail
MODE="$1"; WT="$2"; DRV="$3"; DSHA="$4"; PLAN="$5"; RUNS="$6"; TMPR="$7"; PREFIX="$8"; MAXWALL="$9"; shift 9
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
if ls -A "/run/user/$(id -u)" 2>/dev/null | grep -qE '^(wayland-|hypr|bus$|at-spi$|pipewire)' \
   || ls -A /tmp/.X11-unix 2>/dev/null | grep -q .; then
  echo "refusing: host desktop sockets visible (run as: hostless hostless-strict run_chunks.sh ...)" >&2; exit 95
fi
LANES="${N04_LANES:?set N04_LANES}"; LOCKDIR="${N04_LOCKDIR:?set N04_LOCKDIR}"
LOCK="$LOCKDIR/quiet-lane.lock"; CARGO_LOCK="$LOCKDIR/cargo-build.lock"
[ -e "$LOCK" ] || { echo "refusing: quiet-lane lock $LOCK missing" >&2; exit 94; }
HERE="$(cd "$(dirname "$0")" && pwd)"
export TMPDIR="$TMPR"
mkdir -p "$RUNS/chunks" "$TMPR/sess"
blocks=("$@"); names=()
for b in "${blocks[@]}"; do [ "$b" = "--no-load-gate" ] || names+=("$b"); done
all_done() {
  local b
  for b in "${names[@]}"; do
    compgen -G "$RUNS/$PREFIX-$b/DONE" > /dev/null || compgen -G "$RUNS/$PREFIX-$b-r*/DONE" > /dev/null || return 1
  done
  return 0
}
t0=$(date +%s); n=0; fails=0
while ! all_done; do
  now=$(date +%s)
  if [ $((now - t0)) -gt "$MAXWALL" ]; then echo "[$(date -u +%FT%T.%3NZ)] max wall reached; rounds left" >&2; exit 2; fi
  n=$((n + 1)); while [ -e "$RUNS/chunks/$PREFIX-c$(printf %02d $n).session.log" ]; do n=$((n + 1)); done
  chunk="$PREFIX-c$(printf %02d $n)"; slog="$RUNS/chunks/$chunk.session.log"
  session=(env CUA_SESSION_ATSPI=1
           "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1 TMPDIR=$TMPR/sess"
           "$LANES/cua-x11-session.sh"
           "$HERE/run_block_n04.sh" "$WT" "$DRV" "$DSHA" "$PLAN" "$RUNS" "$TMPR/work" "$PREFIX" "$chunk" "${blocks[@]}")
  echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk mode=$MODE loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  if [ "$MODE" = exclusive ]; then
    ( cd "$WT" && flock "$CARGO_LOCK" "$LANES/bin/quiet-timed" "$chunk" timeout -k 15 600 "${session[@]}" ) > "$slog" 2>&1
    rc=$?
  else
    ( cd "$WT" && flock -s "$LOCK" bash -c '
        acq="$(date -u +%FT%T.%3NZ)"; la="$(cut -d" " -f1-3 /proc/loadavg)"
        label="$1"; lane_ledger="$2"; global_ledger="$3"; shift 3
        "$@"; rc=$?
        line=$(printf "{\"lane\":\"N-04\",\"label\":\"%s\",\"mode\":\"shared\",\"pid\":%d,\"acquired\":\"%s\",\"released\":\"%s\",\"rc\":%d,\"loadavg_at_acquire\":\"%s\"}" \
          "$label" "$$" "$acq" "$(date -u +%FT%T.%3NZ)" "$rc" "$la")
        printf "%s\n" "$line" >> "$lane_ledger"; printf "%s\n" "$line" >> "$global_ledger"
        exit $rc' _ "$chunk" "$RUNS/lock-ledger-shared.jsonl" "$LOCKDIR/quiet-lane-ledger.jsonl" timeout -k 15 600 "${session[@]}" ) \
      > "$slog" 2>&1
    rc=$?
  fi
  echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk rc=$rc $(grep -m1 '^\[n04\] chunk=' "$slog" | cut -c1-200)"
  case "$rc" in
    0) fails=0 ;;
    75) fails=0; sleep 90 ;;
    76|93) fails=0; sleep 5 ;;
    *) fails=$((fails + 1)); echo "[$(date -u +%FT%T.%3NZ)] chunk $chunk failed rc=$rc (kept; consecutive $fails)" >&2
       [ "$fails" -ge 4 ] && { echo "stopping after 4 consecutive failed chunks" >&2; exit 3; }
       sleep 30 ;;
  esac
done
echo "[$(date -u +%FT%T.%3NZ)] all rounds done: ${names[*]}"
