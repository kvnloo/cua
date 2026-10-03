#!/usr/bin/env bash
# Owner-ruled rerun R10c (CALIB2-AMEND-R10C.json): R10 with the setup error fixed. The burner dose is derived
# from the LOGICAL CPU count (getconf, which OMP_NUM_THREADS does not cap; nproc reported 10 and caused R10's
# failed manipulation) at 1.5 burners per logical CPU, so runnable tasks exceed the CPUs. 2 assessable repeats
# on the R10c ledger; a repeat that stops INFRA before its confirm task rows exist is replaced by the next
# repeat number, at most twice (pre-registered).
set -uo pipefail
D=<tmp>/ar-calib2; T=$D/tools; LOG=$D/run_r10c.log
LCPU=$(getconf _NPROCESSORS_ONLN)
[ "$LCPU" = 20 ] || { echo "ABORT: logical CPUs=$LCPU, prereg expects 20" >> $LOG; exit 2; }
N=$(( LCPU * 3 / 2 ))
echo "{\"logical_cpus\":$LCPU,\"nproc\":$(nproc),\"burners\":$N,\"utc\":\"$(date -u +%FT%TZ)\"}" >> $LOG
[ -f $D/cal2-amend2-results.jsonl ] || cp $D/cal2-amend-results.jsonl $D/cal2-amend2-results.jsonl
assessable() { [ -d "$D/evals/$1/confirm/raw" ] && ls "$D/evals/$1/confirm/raw/"*.jsonl >/dev/null 2>&1; }
ok=0; r=1
while [ $ok -lt 2 ] && [ $r -le 4 ]; do
  eid=$(printf 'ar-20261002-cal2-%s-r%02d' delete50-load30c "$r")
  if [ ! -f $D/evals/$eid/final.json ]; then
    AR_CAL_LOAD=$N AR_CAL_LEDGER=$D/cal2-amend2-results.jsonl $T/calib_eval.sh delete50 22 "$r" delete50-load30c >> $LOG 2>&1
  fi
  if assessable $eid; then ok=$((ok+1)); else echo "{\"eval_id\":\"$eid\",\"not_assessable\":true}" >> $LOG; fi
  r=$((r+1))
done
echo R10C_DONE >> $LOG
