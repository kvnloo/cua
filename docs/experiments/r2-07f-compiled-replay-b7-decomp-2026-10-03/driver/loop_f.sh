#!/usr/bin/env bash
# usage (on the host, through hostless): loop_f.sh <plan> <lock-mode> <out-dir> [extra runner args...]
# Bookkeeping only: re-runs run_chunk_f.sh for one plan until the runner reports every unit done (rc 0).
# rc 74 (cargo lock busy / not acquired), 75 (load gate ended the chunk), 76 (chunk budget) and 97 (session
# probe failed) are retried after a 20-40 s pause with a new chunk id; any other rc stops the loop. At most
# MAX_CHUNKS chunks. Machine paths come from the environment (R2_07F_LANES, R2_07F_LOCKDIR, R2_07F_LEDGER,
# R2_07F_WT).
# Resume bookkeeping (R2-07fR, wave 8; env-gated by R2_07F_QUEUE_GATE=1, default unchanged): before each chunk
# the loop waits until the 1-min loadavg is <= 4.0 and (exclusive) the cargo-build lock is free or (shared) no
# EXCLUSIVE waiter is queued on the quiet-lane lock; while an exclusive chunk is queued inside bin/quiet-timed
# (its child is the waiting `flock -x`), the time counts as waiting too. Cumulative waiting (all plans) lives in
# R2_07F_WAITSTATE; every 15 min of waiting a read-only holder snapshot (pid, ppid, elapsed, executable name of
# every holder/waiter on the quiet-lane lock) goes to R2_07F_LOCKSNAP/holders.jsonl. At 8 h of cumulative
# waiting the loop stops with rc 98 (BLOCKED); a still-queued waiter of this loop (its own process) is ended.
# Measurement is unchanged: the runner's own per-round load gate still decides every round.
set -uo pipefail
PLAN="$1"; MODE="$2"; OUT="$3"; shift 3
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
WT="${R2_07F_WT:?}"; LANES="${R2_07F_LANES:?}"
D="$WT/docs/experiments/r2-07f-compiled-replay-b7-decomp-2026-10-03/driver"
MAX_CHUNKS="${MAX_CHUNKS:-40}"
mkdir -p "$OUT"
GATE="${R2_07F_QUEUE_GATE:-0}"; PFX="${R2_07F_LABEL_PREFIX:-r207f}"; LOCKDIR="${R2_07F_LOCKDIR:?}"
WSTATE="${R2_07F_WAITSTATE:-$OUT/wait-state}"; SNAP="${R2_07F_LOCKSNAP:-$OUT/locks}"; WAIT_CAP=28800
QINO="$(stat -c %i "$LOCKDIR/quiet-lane.lock")"
waited() { cat "$WSTATE" 2>/dev/null || echo 0; }
snapshot() {  # read-only: pid, ppid, elapsed, executable name of every holder/waiter on the quiet-lane lock
  mkdir -p "$SNAP"; local hs="" l pid st info
  while read -r l; do
    pid=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^(READ|WRITE)$/){print $(i+1); exit}}' <<<"$l")
    st=$([[ "$l" == *"->"* ]] && echo waiting || echo held)
    info=$(ps -o ppid=,etimes=,comm= -p "$pid" 2>/dev/null | awk '{printf "%s,%s,\"%s\"", $1, $2, $3}')
    hs+="{\"pid\":$pid,\"mode\":\"$(grep -o -E 'READ|WRITE' <<<"$l" | head -1)\",\"state\":\"$st\",\"ppid_elapsed_s_comm\":[${info:-null}]},"
  done < <(grep -E -- ":$QINO " /proc/locks)
  printf '{"utc":"%s","reason":"%s","plan":"%s","waited_total_s":%s,"loadavg":"%s","holders":[%s]}\n' \
    "$(date -u +%FT%TZ)" "$1" "$PLAN" "$(waited)" "$(cut -d' ' -f1-3 /proc/loadavg)" "${hs%,}" >> "$SNAP/holders.jsonl"
}
add_wait() {  # add $1 s of waiting; snapshot at every 15-min boundary; rc 98 past the 8 h cap
  local before after; before=$(waited); after=$((before + $1)); echo "$after" > "$WSTATE"
  [ $((before / 900)) -ne $((after / 900)) ] && snapshot "15min-waiting"
  [ "$after" -lt "$WAIT_CAP" ]
}
pregate() {  # queue only at loadavg <= 4.0 with the cargo lock free (exclusive) / no exclusive waiter (shared)
  while :; do
    local l1; l1=$(cut -d' ' -f1 /proc/loadavg)
    if awk -v l="$l1" 'BEGIN{exit !(l <= 4.0)}'; then
      if [ "$MODE" = exclusive ]; then flock -n "$LOCKDIR/cargo-build.lock" true && return 0
      else grep -E -q -- "-> FLOCK +ADVISORY +WRITE +[0-9]+ +[0-9a-f]+:[0-9a-f]+:$QINO " /proc/locks || return 0; fi
    fi
    sleep 15; add_wait 15 || return 98
  done
}
for i in $(seq 1 "$MAX_CHUNKS"); do
  chunk="${PLAN}-$(date -u +%H%M%S)-$i"
  if [ "$GATE" = 1 ]; then
    pregate || { snapshot "8h-cap"; echo "LOOP_BLOCKED $PLAN waited=$(waited)s"; exit 98; }
    chunk="${PLAN}-$(date -u +%H%M%S)-$i"
  fi
  "$D/run_chunk_f.sh" "$chunk" "$MODE" "$WT" "$D/r2_07f.py" --driver "$LANES/bin/cua-driver-b07-231f6e8bb" \
    --driver-sha256 6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa \
    --out "$OUT" --plan "$PLAN" --chunk "$chunk" "$@" >> "$OUT/chunk-$chunk.log" 2>&1 &
  cpid=$!; capped=0
  if [ "$GATE" = 1 ] && [ "$MODE" = exclusive ]; then
    while kill -0 "$cpid" 2>/dev/null; do  # count the time this loop's quiet-timed waits in its `flock -x`
      qt=$(pgrep -f -- "quiet-timed $PFX-$chunk( |$)" | head -1)
      fw=""; [ -n "$qt" ] && fw=$(pgrep -P "$qt" -x flock | while read -r c; do
        [[ "$(tr '\0' ' ' < /proc/$c/cmdline 2>/dev/null)" == "flock -x 9 " ]] && echo "$c"; done | head -1)
      if [ -n "$qt" ] && [ -z "$fw" ] && ! pgrep -P "$qt" -x flock >/dev/null; then sleep 1; continue; fi
      [ -n "$qt" ] && [ -z "$fw" ] && break  # acquired: the child is now the cargo-lock flock
      sleep 5
      if [ -n "$fw" ] && ! add_wait 5; then capped=1; kill "$fw" 2>/dev/null; break; fi
    done
  fi
  wait "$cpid"; rc=$?
  if [ "$capped" = 1 ]; then snapshot "8h-cap"; echo "LOOP_BLOCKED $PLAN waited=$(waited)s rc=$rc"; exit 98; fi
  echo "[$(date -u +%FT%T.%3NZ)] loop $PLAN chunk $chunk rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)" | tee -a "$OUT/loop.log"
  case "$rc" in
    0) echo "LOOP_DONE $PLAN"; exit 0 ;;
    74|75|76|97) sleep "$((20 + RANDOM % 21))" ;;
    *) echo "LOOP_STOP $PLAN rc=$rc"; exit "$rc" ;;
  esac
done
echo "LOOP_MAX_CHUNKS $PLAN"; exit 1
