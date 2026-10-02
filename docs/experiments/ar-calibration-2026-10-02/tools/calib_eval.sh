#!/usr/bin/env bash
# One calibration evaluation, exactly as the calibrated proposer pipeline runs it (run under hostless):
#   G0 (ar-eval g0) -> G1 (rows from g1-all.sh) -> screen (24 pairs, tools/screen.py) ->
#   [ranks] confirm task+spot sessions -> interim (ar-eval evaluate on a scratch ledger copy) ->
#   [no failure before G8] browser spot + 300-trial soak sessions -> final ar-eval evaluate -> ledger.
# usage: calib_eval.sh <name> <index> <repeat>
set -uo pipefail
NAME=$1; IDX=$2; REP=$3
D=<tmp>/ar-calib; L=<lanes>; H=$L/ar-harness; A=$H/harness/ar
REPO=$L/ar-calib; CH=457bc65d45b2a87ac080b281ea777f8914002c29; HC=2615af74f3517200e86004ac924c06d07ddf2ae4
IC=<mnt>/cargo-targets/ar-itemcheck/release/itemcheck
TAU=$H/docs/experiments/ar-aa-2026-10-02/tau.json
CHAMP=$L/bin/cua-driver-ar-base-457bc65d4
LEDGER=$D/cal-results.jsonl
N01="none: no N-01 packet exists (artifacts/r2/n-01 empty, artifacts/r2/N-01R holds plans and pilots only) at calibration time"
export TMPDIR=<tmp> PYTHONDONTWRITEBYTECODE=1 AR_LANES=$L
EID=$(printf 'ar-20261002-cal-%s-r%02d' "$NAME" "$REP"); E=$D/evals/$EID
SSEED=$((20261002 + 1000*IDX + 10*REP + 1)); CSEED=$((20261002 + 1000*IDX + 10*REP + 2))
mkdir -p $E
ms() { date +%s%3N; }
stamp() { printf '{"eval_id":"%s","stage":"%s","t_ms":%d,"utc":"%s"%s}\n' "$EID" "$1" "$(ms)" "$(date -u +%FT%TZ)" "${2:-}" >> $E/stages.jsonl; }
final() { printf '{"eval_id":"%s","name":"%s","repeat":%d,"stage":"%s","verdict":"%s","failed_gate":%s,"utc":"%s"}\n' \
  "$EID" "$NAME" "$REP" "$1" "$2" "$3" "$(date -u +%FT%TZ)" > $E/final.json; stamp done; cat $E/final.json; exit 0; }
stamp start ",\"screen_seed\":$SSEED,\"confirm_seed\":$CSEED"

REQ=$(awk -v n="$NAME" '$1==n{print $2}' $D/submit.log)
[ -n "$REQ" ] || { echo "no request for $NAME"; exit 2; }

# G0 (re-run per evaluation)
python3 $A/ar-eval g0 --repo $REPO --champion $CH --candidate ar/calib/$NAME --itemcheck $IC --out $E/g0.inputs.json > $E/g0.json
stamp g0
if [ "$(jq -r .pass $E/g0.json)" != true ]; then final g0 REJECT '"G0"'; fi

# G1 rows (built and tested once per branch by g1-all.sh)
while ! grep -q "\"name\":\"$NAME\"" $D/g1/timing.jsonl 2>/dev/null; do sleep 20; done
LABEL=$(jq -r --arg n "$NAME" 'select(.name==$n) | .label' $D/g1/timing.jsonl | tail -1)
CAND=$L/bin/cua-driver-$LABEL
cp $D/g1/$NAME.rows.jsonl $E/g1.rows.jsonl
stamp g1_ready
G1OK=$(python3 -c "
import json,sys; sys.path.insert(0,'$A'); from areval import gates
rows=[json.loads(x) for x in open('$E/g1.rows.jsonl') if x.strip()]
print('1' if gates.g1(rows,['cua-driver-core --lib','platform-linux --lib'])['pass'] else '0')")
if [ "$G1OK" != 1 ] || [ ! -x "$CAND" ]; then final g1 REJECT '"G1"'; fi

python3 $A/ar-eval prereg --request "$REQ" --eval-id $EID --champion-commit $CH \
  --candidate-commit "$(git -C $REPO rev-parse ar/calib/$NAME)" --champion-bin $CHAMP --candidate-bin $CAND \
  --tau $TAU --harness-commit $HC --seed $CSEED --soak 300 --n01 "$N01" --out $E/prereg.json > /dev/null || exit 3

# Screen: one fresh session of 24 pairs
python3 $A/runner/plan.py --eval-id $EID-scr --champion $CHAMP --candidate $CAND --pairs 24 --seed $SSEED --out $E/screen-plan.json > /dev/null
stamp screen_start
python3 $A/runner/run_blocks.py --plan $E/screen-plan.json --out-dir $E/screen --wt $H --label $EID-scr > $E/screen-blocks.out 2>&1
src=$?
stamp screen_end ",\"rc\":$src"
if [ $src -ne 0 ]; then final screen INFRA null; fi
python3 $D/tools/screen.py --harness $A --prereg $E/prereg.json --rows $E/screen/raw/*.jsonl --build-rows $E/g1.rows.jsonl \
  --g0 $E/g0.json --seed $SSEED --out $E/screen.json > /dev/null
V=$(jq -r .verdict $E/screen.json)
if [ "$V" != RANKS ]; then final screen "$V" "$(jq -c .failed_gate $E/screen.json)"; fi

# Confirm: fresh plan; task + spot_gtk3_text sessions first
python3 $A/runner/plan.py --eval-id $EID-cnf --champion $CHAMP --candidate $CAND --pairs 38 --spot-pairs 10 \
  --spot-browser-pairs 10 --soak 300 --seed $CSEED --out $E/confirm-plan.json > /dev/null
TASKS=$(jq -r '[.sessions[] | select(any(.trials[]; .kind=="task" and .pair_id != null)) | .session] | join(",")' $E/confirm-plan.json)
REST=$(jq -r '[.sessions[] | select(all(.trials[]; .kind!="task" or .pair_id == null)) | .session] | join(",")' $E/confirm-plan.json)
stamp confirm_task_start ",\"sessions\":\"$TASKS\""
python3 $A/runner/run_blocks.py --plan $E/confirm-plan.json --out-dir $E/confirm --wt $H --label $EID-cnf --sessions $TASKS > $E/confirm-blocks.out 2>&1
crc=$?
stamp confirm_task_end ",\"rc\":$crc"
if [ $crc -ne 0 ]; then final confirm INFRA null; fi
cp -f $LEDGER $E/scratch-ledger.jsonl 2>/dev/null || : > $E/scratch-ledger.jsonl
python3 $A/ar-eval evaluate --prereg $E/prereg.json --rows $E/confirm/raw/*.jsonl --build-rows $E/g1.rows.jsonl \
  --g0-inputs $E/g0.inputs.json --results $E/scratch-ledger.jsonl > $E/interim.json
FG=$(jq -r .failed_gate $E/interim.json)
if [ "$FG" = G8 ] || [ "$FG" = GS ]; then
  stamp confirm_rest_start ",\"sessions\":\"$REST\""
  python3 $A/runner/run_blocks.py --plan $E/confirm-plan.json --out-dir $E/confirm --wt $H --label $EID-cnf --sessions $REST >> $E/confirm-blocks.out 2>&1
  rrc=$?
  stamp confirm_rest_end ",\"rc\":$rrc"
  if [ $rrc -ne 0 ]; then final confirm INFRA null; fi
fi
python3 $A/ar-eval evaluate --prereg $E/prereg.json --rows $E/confirm/raw/*.jsonl --build-rows $E/g1.rows.jsonl \
  --g0-inputs $E/g0.inputs.json --results $LEDGER > $E/evaluate.json
final confirm "$(jq -r .verdict $E/evaluate.json)" "$(jq -c .failed_gate $E/evaluate.json)"
