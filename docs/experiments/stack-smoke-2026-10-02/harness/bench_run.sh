#!/usr/bin/env bash
# bench_run.sh <backend> <frozen_requests.jsonl> <out.json>
# One quiet-lane timing phase for one shadow backend. Invoke as:
#   quiet-timed stack-smoke-h5-<backend> hostless bench_run.sh <backend> <frozen> <out>
# Environment (from the operator, never committed): Z0_WT Z0_VENV HF_HUB_DIR NANOJEV_CKPT JULIA_PY BENCH_TMP
set -euo pipefail
B="$1"; REQ="$2"; OUT="$3"
H="$(cd "$(dirname "$0")" && pwd)"
SC_HOME="$BENCH_TMP/home-$B"; rm -rf "$SC_HOME"; mkdir -p "$SC_HOME/.cache/huggingface" "$BENCH_TMP/z0int-home-$B" "$BENCH_TMP/tmp"
ln -s "$HF_HUB_DIR" "$SC_HOME/.cache/huggingface/hub"   # only the model hub; no token files
T0="$(date +%s.%N)"
exec env -i PATH="$Z0_VENV/bin:/usr/bin:/bin" HOME="$SC_HOME" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 TMPDIR="$BENCH_TMP/tmp" \
  Z0INT_HOME="$BENCH_TMP/z0int-home-$B" Z0INT_NANOJEV_CHECKPOINT="$NANOJEV_CKPT" Z0INT_JULIA_PYTHON="$JULIA_PY" \
  Z0INT_LAYA_DEVICE=cpu Z0INT_JULIA_DEVICE=cpu Z0INT_DECIDER_DEVICE=cuda LANG=C.UTF-8 STACK_T0="$T0" \
  "$Z0_VENV/bin/python" "$H/bench_backends.py" --backend "$B" --requests "$REQ" --out "$OUT" --z0-wt "$Z0_WT"
