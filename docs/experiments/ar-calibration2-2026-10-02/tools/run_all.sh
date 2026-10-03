#!/usr/bin/env bash
# Runs every calibration-2 evaluation in the pre-registered order (run under hostless).
# usage: run_all.sh
set -uo pipefail
T=<tmp>/ar-calib2/tools; D=<tmp>/ar-calib2
list=("sleep20 1 1" "sleep50 2 1")
for r in 1 2 3 4 5 6 7 8 9 10; do list+=("delete50 3 $r"); done
list+=("success-early 4 1" "g0-frozen-item 5 1" "g0-test-item 6 1" "g0-trace-line 7 1" "g0-scanner 8 1")
for i in 01 02 03 04 05 06 07 08 09 10; do list+=("noop$i $((8 + 10#$i)) 1"); done
list+=("new-socket 19 1")
for item in "${list[@]}"; do
  set -- $item
  eid=$(printf 'ar-20261002-cal2-%s-r%02d' "$1" "$3")
  [ -f $D/evals/$eid/final.json ] && continue
  $T/calib_eval.sh "$1" "$2" "$3" >> $D/run_all.log 2>&1
done
# R10: delete50 under planted load (10 CPU burners inside each screen/confirm task block)
for r in 1 2; do
  eid=$(printf 'ar-20261002-cal2-%s-r%02d' delete50-load "$r")
  [ -f $D/evals/$eid/final.json ] && continue
  AR_CAL_LOAD=10 $T/calib_eval.sh delete50 20 "$r" delete50-load >> $D/run_all.log 2>&1
done
echo ALL_DONE >> $D/run_all.log
