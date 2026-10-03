#!/usr/bin/env bash
# Amendment row R10b (CALIB2-AMEND-R10B.json): delete50 under 30 CPU burners, 2 repeats, on the amendment ledger.
set -uo pipefail
D=<tmp>/ar-calib2; T=$D/tools
for r in 1 2; do
  eid=$(printf 'ar-20261002-cal2-%s-r%02d' delete50-load30 "$r")
  [ -f $D/evals/$eid/final.json ] && continue
  AR_CAL_LOAD=30 AR_CAL_LEDGER=$D/cal2-amend-results.jsonl $T/calib_eval.sh delete50 21 "$r" delete50-load30 >> $D/run_r10b.log 2>&1
done
echo R10B_DONE >> $D/run_r10b.log
