#!/usr/bin/env bash
# run_scoring.sh: freeze -> build -> score (one process per backend per lane) -> evaluate -> analyze.
# Run on the plain shell; every step that executes code goes through $HOSTLESS. Latency-bearing
# scoring processes are wrapped in $QUIET (exclusive quiet-lane lock + ledger). Required env:
#   HOSTLESS QUIET HERMES_WT Z0_WT Z0_VENV PACKET COLLECT RUNS WORK NANOJEV_CKPT JULIA_PY
set -euo pipefail
: "${HOSTLESS:?}" "${QUIET:?}" "${HERMES_WT:?}" "${Z0_WT:?}" "${Z0_VENV:?}" "${PACKET:?}" "${COLLECT:?}" "${RUNS:?}" "${WORK:?}"
: "${NANOJEV_CKPT:?}" "${JULIA_PY:?}"
H="$PACKET/harness"; PY="$Z0_VENV/bin/python"
mkdir -p "$WORK"/{examples,scored/api,scored/turn,eval/api,eval/turn,analysis,scoring-logs,tmp,z0int-home,controls}
step() { echo "[$(date -u +%FT%TZ)] $*"; }

if [ ! -f "$WORK/dataset/MANIFEST.json" ]; then
  step freeze
  "$HOSTLESS" python3 "$H/freeze.py" "$PACKET/workload/tasks.jsonl" "$COLLECT" "$RUNS" "$WORK/dataset" "$WORK/identities.json"
fi
step build
"$HOSTLESS" "$PY" "$HERMES_WT/lab/z0_hermes_observer/shadow_api_failure.py" "$WORK/dataset/events.jsonl" \
  --output "$WORK/examples/api-examples.jsonl" --audit-output "$WORK/examples/api-audit.json"
"$HOSTLESS" "$PY" "$H/build_turn_examples.py" "$WORK/dataset" "$Z0_WT" \
  --output "$WORK/examples/turn-examples.jsonl" --audit-output "$WORK/examples/turn-audit.json"

SCORER_ENV=(env HF_HUB_OFFLINE=1 TMPDIR="$WORK/tmp" Z0INT_HOME="$WORK/z0int-home" Z0INT_NANOJEV_CHECKPOINT="$NANOJEV_CKPT"
            Z0INT_JULIA_PYTHON="$JULIA_PY" Z0INT_LAYA_DEVICE=cpu Z0INT_JULIA_DEVICE=cpu)
gpu_free_mib() { "$HOSTLESS" nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits | awk -F', ' '{print $1-$2}'; }
score() {  # score <lane> <row> <backend> [need_gpu_mib]
  local lane="$1" row="$2" backend="$3" need="${4:-0}" log="$WORK/scoring-logs/$1-$2.log"
  [ -s "$WORK/scored/$lane/scored-$row.jsonl" ] && { step "skip $lane/$row (exists)"; return 0; }
  if [ "$need" -gt 0 ]; then
    for _ in $(seq 1 60); do [ "$(gpu_free_mib)" -ge "$need" ] && break; step "wait GPU ($(gpu_free_mib) MiB free < $need)"; sleep 30; done
  fi
  step "score $lane/$row ($backend)"
  "$QUIET" "samples-score-$lane-$row" "$HOSTLESS" "${SCORER_ENV[@]}" bash -c '
      echo "loadavg_before $(cat /proc/loadavg)"; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | sed "s/^/gpu_before /"
      "$@"; rc=$?
      echo "loadavg_after $(cat /proc/loadavg)"; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null | sed "s/^/gpu_after /"
      exit $rc' _ "$PY" "$H/score_lane.py" "$HERMES_WT" "$WORK/examples/$lane-examples.jsonl" "$backend" \
      "$WORK/scored/$lane/scored-$row.jsonl" > "$log" 2>&1 || step "score $lane/$row rc=$? (see log)"
}
for lane in turn api; do
  score "$lane" laya_421m laya_421m
  score "$lane" julia_1 julia_1
  score "$lane" qwen_3b_baseline ollama:qwen2.5:3b
done
for lane in turn api; do
  score "$lane" decider_2b decider_2b 4800
  score "$lane" nanojev nanojev 3000
done
step "control: fail-open (dead-port Ollama adapter), turn lane"
[ -s "$WORK/scored/turn/scored-failopen_ollama_deadport.jsonl" ] || "$HOSTLESS" env Z0INT_OLLAMA_BASE_URL=http://127.0.0.1:9 "$PY" "$H/score_lane.py" "$HERMES_WT" \
  "$WORK/examples/turn-examples.jsonl" ollama:qwen2.5:3b "$WORK/scored/turn/scored-failopen_ollama_deadport.jsonl" \
  > "$WORK/controls/failopen.log" 2>&1; echo "rc=$?" >> "$WORK/controls/failopen.log"

step evaluate
for lane in api turn; do
  qid=$([ "$lane" = api ] && echo api.attempt_will_fail || echo verification_needed)
  for f in "$WORK/scored/$lane"/scored-*.jsonl; do
    row="$(basename "$f" .jsonl)"; row="${row#scored-}"
    "$HOSTLESS" "$PY" "$HERMES_WT/lab/z0_hermes_observer/evaluate_shadow.py" "$f" --question-id "$qid" \
      --output "$WORK/eval/$lane/eval-$row.json" > /dev/null
  done
  "$HOSTLESS" python3 "$H/analyze.py" "$HERMES_WT" "$qid" "$WORK/examples/$lane-examples.jsonl" "$WORK/scored/$lane" \
    "$WORK/dataset/runs.jsonl" "$WORK/analysis/$lane-analysis.json"
done
step done
