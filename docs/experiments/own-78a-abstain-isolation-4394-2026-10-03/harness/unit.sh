#!/usr/bin/env bash
# usage: hostless unit.sh <examples-dir> <out-dir>
# Runs the jev-use CI unit steps credential-free: TYPESAFE_* and CUA_S1_* are removed from the env.
# Must run under bin/hostless (refuses otherwise).
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
EX="$1"; OUT="$2"; mkdir -p "$OUT"
[ -n "${LANE_TOOL_PATH:-}" ] && export PATH="$LANE_TOOL_PATH:$PATH"   # node/uv locations, passed by the caller
for v in $(env | sed -n 's/^\(TYPESAFE_[A-Z_]*\|CUA_S1_[A-Z_]*\)=.*/\1/p'); do unset "$v"; done
cd "$EX"
step() { local name="$1"; shift; local t0=$(date +%s%N); "$@" >"$OUT/$name.log" 2>&1; local rc=$?; printf '%-28s rc=%d %6d ms\n' "$name" "$rc" $(( ($(date +%s%N)-t0)/1000000 )) | tee -a "$OUT/steps.txt"; }
: > "$OUT/steps.txt"
echo "credential_env_present=$(env | grep -c '^\(TYPESAFE_\|CUA_S1_\)')" > "$OUT/env.txt"
echo "node=$(node --version) python=$(.venv/bin/python --version 2>&1)" >> "$OUT/env.txt"
step python-unittest-discover uv run --frozen python -m unittest discover -s python/tests -v
step verify_choice_cli uv run --frozen python verify_choice_cli.py
step verify_decision_cli-mock uv run --frozen python verify_decision_cli.py --model mock
step verify_choice_cli-v2 uv run --frozen python verify_choice_cli.py --request-version v2
step verify_decision_cli-native uv run --frozen python verify_decision_cli.py --model mock --fixture native
step ts-npm-test npm test
step ts-typecheck npm run typecheck
