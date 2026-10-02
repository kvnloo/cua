#!/usr/bin/env bash
# Runs ar-eval g0 on every calibration branch (under hostless). Writes g0/<name>.inputs.json + g0/<name>.json.
set -uo pipefail
D=<tmp>/ar-calib; WT=<lanes>/ar-harness
REPO=<lanes>/ar-calib; CH=457bc65d45b2a87ac080b281ea777f8914002c29
IC=<mnt>/cargo-targets/ar-itemcheck/release/itemcheck
export PYTHONDONTWRITEBYTECODE=1 TMPDIR=<tmp>
for name in "$@"; do
  t0=$(date +%s%N)
  python3 $WT/harness/ar/ar-eval g0 --repo $REPO --champion $CH --candidate ar/calib/$name --itemcheck $IC \
    --out $D/g0/$name.inputs.json > $D/g0/$name.json; rc=$?
  t1=$(date +%s%N)
  printf '{"name":"%s","rc":%d,"wall_ms":%d}\n' "$name" "$rc" "$(( (t1 - t0) / 1000000 ))" >> $D/g0/timing.jsonl
done
