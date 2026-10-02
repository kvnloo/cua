#!/usr/bin/env bash
# run_scoring.sh: build -> score (one process per backend per lane) -> evaluate -> analyze, over the FROZEN dataset.
# Adapted from the SAMPLES run_scoring.sh. Run on the plain shell; every step that executes code goes through
# $HOSTLESS, and every scoring process is wrapped in $QUIET (exclusive quiet-lane lock + ledger) so the latency
# numbers are quiet-lane numbers. GPU order (PREREG scoring_and_gpu_plan): CPU rows, then the Qwen logprob row
# (needs the chat model on $OLLAMA), then the chat model is unloaded and nanojev and decider_2b run alone.
# Required env: HOSTLESS QUIET HERMES_WT Z0_VENV PACKET WORK NANOJEV_CKPT JULIA_PY OLLAMA QWEN_MODEL Z0_WT
set -euo pipefail
: "${HOSTLESS:?}" "${QUIET:?}" "${HERMES_WT:?}" "${Z0_VENV:?}" "${PACKET:?}" "${WORK:?}" "${NANOJEV_CKPT:?}"
: "${JULIA_PY:?}" "${OLLAMA:?}" "${QWEN_MODEL:?}" "${Z0_WT:?}"
H="$PACKET/harness"; PY="$Z0_VENV/bin/python"; DATA="$PACKET/dataset"
mkdir -p "$WORK"/{examples,scored/api,scored/turn,eval/api,eval/turn,analysis,scoring-logs,tmp,z0int-home,controls,gpu}
step() { echo "[$(date -u +%FT%T.%3NZ)] $*"; }
[ -f "$DATA/MANIFEST.json" ] || { echo "dataset not frozen" >&2; exit 2; }

step build
"$HOSTLESS" "$PY" "$HERMES_WT/lab/z0_hermes_observer/shadow_api_failure.py" "$DATA/events.jsonl" \
  --output "$WORK/examples/api-examples.jsonl" --audit-output "$WORK/examples/api-audit.json"
"$HOSTLESS" "$PY" "$H/build_turn_examples.py" "$DATA" "$Z0_WT" \
  --output "$WORK/examples/turn-examples.jsonl" --audit-output "$WORK/examples/turn-audit.json"

SCORER_ENV=(env HF_HUB_OFFLINE=1 TMPDIR="$WORK/tmp" Z0INT_HOME="$WORK/z0int-home" Z0INT_NANOJEV_CHECKPOINT="$NANOJEV_CKPT"
            Z0INT_JULIA_PYTHON="$JULIA_PY" Z0INT_LAYA_DEVICE=cpu Z0INT_JULIA_DEVICE=cpu Z0INT_OLLAMA_BASE_URL="$OLLAMA"
            NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost)
gpu_free_mib() { "$HOSTLESS" nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | awk -F', ' '{print $1-$2}'; }
ollama_ps() { "$HOSTLESS" curl -s --noproxy '*' "$OLLAMA/api/ps"; }
gpu_snapshot() {  # gpu_snapshot <label>
  { echo "at $(date -u +%FT%T.%3NZ) label=$1"; "$HOSTLESS" nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader;
    echo "ollama_ps $(ollama_ps)"; } >> "$WORK/gpu/gpu-snapshots.log"
}
score() {  # score <lane> <row> <backend> [need_gpu_mib]
  local lane="$1" row="$2" backend="$3" need="${4:-0}" log="$WORK/scoring-logs/$1-$2.log"
  [ -s "$WORK/scored/$lane/scored-$row.jsonl" ] && { step "skip $lane/$row (exists)"; return 0; }
  if [ "$need" -gt 0 ]; then
    for _ in $(seq 1 60); do
      if [ "$(gpu_free_mib)" -ge "$need" ] && [ "$(ollama_ps | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("models", [])))')" = 0 ]; then break; fi
      step "wait GPU ($(gpu_free_mib) MiB free < $need, or a chat model is resident)"; sleep 30
    done
  fi
  gpu_snapshot "before $lane/$row"
  step "score $lane/$row ($backend)"
  "$QUIET" "confirm-score-$lane-$row" "$HOSTLESS" "${SCORER_ENV[@]}" bash -c '
      echo "loadavg_before $(cat /proc/loadavg)"; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | sed "s/^/gpu_before /"
      "$@"; rc=$?
      echo "loadavg_after $(cat /proc/loadavg)"; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | sed "s/^/gpu_after /"
      exit $rc' _ "$PY" "$H/score_lane.py" "$HERMES_WT" "$WORK/examples/$lane-examples.jsonl" "$backend" \
      "$WORK/scored/$lane/scored-$row.jsonl" > "$log" 2>&1 || step "score $lane/$row rc=$? (see log)"
  gpu_snapshot "after $lane/$row"
}

for lane in turn api; do
  score "$lane" laya_421m laya_421m
  score "$lane" julia_1 julia_1
done
for lane in turn api; do
  score "$lane" qwen_7b_logprob "ollama:$QWEN_MODEL"
done
step "control: fail-open (dead-port Ollama adapter), turn lane"
if [ ! -s "$WORK/scored/turn/scored-failopen_ollama_deadport.jsonl" ]; then
  set +e
  "$HOSTLESS" "${SCORER_ENV[@]}" Z0INT_OLLAMA_BASE_URL=http://127.0.0.1:9 "$PY" "$H/score_lane.py" "$HERMES_WT" \
    "$WORK/examples/turn-examples.jsonl" "ollama:$QWEN_MODEL" "$WORK/scored/turn/scored-failopen_ollama_deadport.jsonl" \
    > "$WORK/controls/failopen.log" 2>&1
  echo "rc=$?" >> "$WORK/controls/failopen.log"
  set -e
fi

step "unload chat model $QWEN_MODEL on $OLLAMA (keep_alive=0) for the GPU scorers"
gpu_snapshot "before unload"
"$HOSTLESS" curl -s --noproxy '*' "$OLLAMA/api/generate" -d "{\"model\": \"$QWEN_MODEL\", \"keep_alive\": 0}" > "$WORK/gpu/unload.json"
sleep 5
gpu_snapshot "after unload"
for lane in turn api; do
  score "$lane" nanojev nanojev 3000
done
for lane in turn api; do
  score "$lane" decider_2b decider_2b 4800
done

step evaluate
for lane in api turn; do
  qid=$([ "$lane" = api ] && echo api.attempt_will_fail || echo verification_needed)
  for f in "$WORK/scored/$lane"/scored-*.jsonl; do
    row="$(basename "$f" .jsonl)"; row="${row#scored-}"
    "$HOSTLESS" "$PY" "$HERMES_WT/lab/z0_hermes_observer/evaluate_shadow.py" "$f" --question-id "$qid" \
      --output "$WORK/eval/$lane/eval-$row.json" > /dev/null
  done
  "$HOSTLESS" python3 "$H/analyze.py" "$HERMES_WT" "$qid" "$WORK/examples/$lane-examples.jsonl" "$WORK/scored/$lane" \
    "$WORK/analysis/$lane-analysis.json"
done
step done
