#!/usr/bin/env bash
# usage (on the host, through hostless): loop_f.sh <plan> <lock-mode> <out-dir> [extra runner args...]
# Bookkeeping only: re-runs run_chunk_f.sh for one plan until the runner reports every unit done (rc 0).
# rc 74 (cargo lock busy / not acquired), 75 (load gate ended the chunk), 76 (chunk budget) and 97 (session
# probe failed) are retried after a 20-40 s pause with a new chunk id; any other rc stops the loop. At most
# MAX_CHUNKS chunks. Machine paths come from the environment (R2_07F_LANES, R2_07F_LOCKDIR, R2_07F_LEDGER,
# R2_07F_WT).
set -uo pipefail
PLAN="$1"; MODE="$2"; OUT="$3"; shift 3
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
WT="${R2_07F_WT:?}"; LANES="${R2_07F_LANES:?}"
D="$WT/docs/experiments/r2-07f-compiled-replay-b7-decomp-2026-10-03/driver"
MAX_CHUNKS="${MAX_CHUNKS:-40}"
mkdir -p "$OUT"
for i in $(seq 1 "$MAX_CHUNKS"); do
  chunk="${PLAN}-$(date -u +%H%M%S)-$i"
  "$D/run_chunk_f.sh" "$chunk" "$MODE" "$WT" "$D/r2_07f.py" --driver "$LANES/bin/cua-driver-b07-231f6e8bb" \
    --driver-sha256 6f95aef5bab98d59e86e9a064380667907080a276f4339540155463cafb6b4aa \
    --out "$OUT" --plan "$PLAN" --chunk "$chunk" "$@" >> "$OUT/chunk-$chunk.log" 2>&1
  rc=$?
  echo "[$(date -u +%FT%T.%3NZ)] loop $PLAN chunk $chunk rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)" | tee -a "$OUT/loop.log"
  case "$rc" in
    0) echo "LOOP_DONE $PLAN"; exit 0 ;;
    74|75|76|97) sleep "$((20 + RANDOM % 21))" ;;
    *) echo "LOOP_STOP $PLAN rc=$rc"; exit "$rc" ;;
  esac
done
echo "LOOP_MAX_CHUNKS $PLAN"; exit 1
