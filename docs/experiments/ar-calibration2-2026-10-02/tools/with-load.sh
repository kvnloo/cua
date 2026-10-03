#!/usr/bin/env bash
# with-load.sh <n> <cmd...>: run <cmd> with <n> CPU burners (shell busy loops, nice 0) alive for exactly its
# duration (row R10, delete50 under load). Called by run_blocks_loaded.py INSIDE quiet-timed, so the burners
# never run outside the quiet-lane lock. Kills only the burners it started.
set -uo pipefail
n=$1; shift
pids=()
for _ in $(seq 1 "$n"); do ( while :; do :; done ) & pids+=($!); done
echo "[with-load] burners=$n started loadavg=$(cat /proc/loadavg)" >&2
"$@"; rc=$?
echo "[with-load] cmd rc=$rc loadavg=$(cat /proc/loadavg)" >&2
kill "${pids[@]}" 2>/dev/null
wait "${pids[@]}" 2>/dev/null
exit $rc
