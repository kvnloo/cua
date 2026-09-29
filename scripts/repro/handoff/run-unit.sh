#!/usr/bin/env bash
# usage: run-unit.sh <worktree> <outdir>
# Runs the exact "CI: jev-use" unit-python + unit-typescript steps (libs/cua-driver/examples/jev-use).
set -uo pipefail
WT="$1"; OUT="$2"; mkdir -p "$OUT"
export PATH=/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin:/home/kvn/.local/bin:$PATH
export TMPDIR=/mnt/zer0models/cua-lane-tmp
cd "$WT/libs/cua-driver/examples/jev-use"
echo "head=$(git rev-parse HEAD) node=$(node --version) uv=$(uv --version) py=$(uv run --frozen python --version)" | tee "$OUT/env.txt"
step() { # name, cmd...
  local name="$1"; shift
  local t0=$(date +%s%N)
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  local t1=$(date +%s%N)
  printf '%-52s rc=%d  %d ms\n' "$name" "$rc" "$(( (t1 - t0) / 1000000 ))" | tee -a "$OUT/steps.txt"
}
: > "$OUT/steps.txt"
step python-unittest-discover        uv run python -m unittest discover -s python/tests -v
step python-guarded-focused          uv run --frozen python -m unittest discover -s python/tests -p test_guarded_completion.py -v
step verify_choice_cli               uv run --frozen python verify_choice_cli.py
step verify_decision_cli-mock        uv run --frozen python verify_decision_cli.py --model mock
step verify_choice_cli-v2            uv run --frozen python verify_choice_cli.py --request-version v2
step verify_decision_cli-native      uv run --frozen python verify_decision_cli.py --model mock --fixture native
step ts-npm-test                     npm test
step ts-guarded-focused              node --import tsx --test typescript/guarded_completion.test.ts
step ts-typecheck                    npm run typecheck
