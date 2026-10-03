#!/usr/bin/env bash
# R8 positive control: plan + one quiet-timed block per session through feedback_session.py (run under hostless).
# usage: run_feedback.sh <out-dir> <kind: browser|gtk> <pairs> <seed>
set -euo pipefail
OUT=$1; KIND=$2; PAIRS=$3; SEED=$4
L=<lanes>; H=$L/ar-harness; T=<tmp>/ar-calib2/tools
BIN=$L/bin/cua-driver-ar-base-457bc65d4
PY=$H/libs/cua-driver/examples/jev-use/.venv/bin/python
export TMPDIR=<tmp> PYTHONDONTWRITEBYTECODE=1
mkdir -p $OUT/chunks $OUT/raw $OUT/work $OUT/logs
if [ "$KIND" = browser ]; then
  python3 $H/harness/ar/runner/plan.py --eval-id cal2-feedback-browser --champion $BIN --candidate $BIN --pairs 0 \
    --spot-browser-pairs $PAIRS --no-controls --seed $SEED --out $OUT/plan.json
else
  python3 $H/harness/ar/runner/plan.py --eval-id cal2-feedback-gtk --champion $BIN --candidate $BIN --pairs $PAIRS \
    --seed $SEED --out $OUT/plan.json
fi
n=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))['sessions']))" $OUT/plan.json)
for k in $(seq 0 $((n-1))); do
  python3 -c "import json,sys; p=json.load(open(sys.argv[1])); open(sys.argv[2],'w').write(json.dumps(p['sessions'][int(sys.argv[3])]))" $OUT/plan.json $OUT/chunks/s$k.json $k
  pidns=$(python3 -c "import json,sys; print('1' if json.load(open(sys.argv[1]))['pidns'] else '0')" $OUT/chunks/s$k.json)
  pre=(); [ "$pidns" = 1 ] && pre=($H/harness/ar/sandbox/session-pidns.sh)
  t0=$(date +%s%3N)
  set +e
  ( cd $OUT && $L/bin/quiet-timed cal2-feedback-$KIND-s$k "${pre[@]}" env CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 \
      $L/cua-x11-session.sh $PY $T/feedback_session.py --wt $H --chunk $OUT/chunks/s$k.json --out $OUT/raw/s$k.jsonl --work $OUT/work/s$k ) > $OUT/logs/s$k.log 2>&1
  rc=$?
  set -e
  printf '{"session":%d,"label":"cal2-feedback-%s-s%d","rc":%d,"wall_ms":%d,"finished":"%s"}\n' $k $KIND $k $rc $(( $(date +%s%3N) - t0 )) "$(date -u +%FT%TZ)" >> $OUT/blocks.jsonl
done
