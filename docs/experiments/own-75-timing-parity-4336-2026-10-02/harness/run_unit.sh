#!/usr/bin/env bash
# usage (always under bin/hostless): run_unit.sh <worktree> <out-dir> <arm-label>
# Runs the jev-use CI unit gates (Python unittest discovery, the mock CLI verifiers, the TypeScript
# node:test suite and tsc --noEmit) for one source tree with a scrubbed environment: no provider
# credentials, no desktop session. Each suite's full output goes to <out-dir>/<arm>-<suite>.log and
# its exit code to <out-dir>/<arm>-rc.json.
set -uo pipefail
WT="$1"; OUT="$2"; ARM="$3"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under bin/hostless" >&2; exit 97; }
J="$WT/libs/cua-driver/examples/jev-use"
NODE_BIN="${OWN75_NODE_BIN:?set OWN75_NODE_BIN}"
TMPR="${OWN75_TMP:?set OWN75_TMP}"
mkdir -p "$OUT" "$TMPR/$ARM-unit"
clean() {
  env -i HOME="$TMPR/$ARM-unit" PATH="$NODE_BIN:/usr/bin:/bin" LANG=C.UTF-8 \
    TMPDIR="$TMPR/$ARM-unit" "$@"
}
declare -A RC
cd "$J"
clean .venv/bin/python -m unittest discover -s python/tests -v > "$OUT/$ARM-python-unittest.log" 2>&1; RC[python_unittest]=$?
clean .venv/bin/python verify_choice_cli.py > "$OUT/$ARM-verify-choice-cli.log" 2>&1; RC[verify_choice_cli]=$?
clean .venv/bin/python verify_decision_cli.py --model mock > "$OUT/$ARM-verify-decision-cli.log" 2>&1; RC[verify_decision_cli]=$?
clean .venv/bin/python verify_choice_cli.py --request-version v2 > "$OUT/$ARM-verify-choice-cli-v2.log" 2>&1; RC[verify_choice_cli_v2]=$?
clean .venv/bin/python verify_decision_cli.py --model mock --fixture native > "$OUT/$ARM-verify-decision-cli-native.log" 2>&1; RC[verify_decision_cli_native]=$?
clean node --import tsx --test --test-reporter=tap typescript/*.test.ts > "$OUT/$ARM-ts-test.log" 2>&1; RC[ts_test]=$?
clean node node_modules/typescript/bin/tsc --noEmit > "$OUT/$ARM-tsc.log" 2>&1; RC[tsc]=$?
{
  printf '{"arm": "%s", "head": "%s", "jev_use_tree": "%s", "jev_use_dirty": "%s"' "$ARM" \
    "$(git -C "$WT" rev-parse HEAD)" "$(git -C "$WT" rev-parse HEAD:libs/cua-driver/examples/jev-use)" \
    "$(git -C "$WT" status --porcelain --untracked-files=no -- libs/cua-driver/examples/jev-use | wc -l)"
  for k in "${!RC[@]}"; do printf ', "%s": %s' "$k" "${RC[$k]}"; done
  printf '}\n'
} > "$OUT/$ARM-rc.json"
cat "$OUT/$ARM-rc.json"
