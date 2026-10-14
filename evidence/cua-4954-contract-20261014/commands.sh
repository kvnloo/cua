#!/usr/bin/env bash
# Usage: PYTHON=/path/to/prepared/python bash commands.sh ORIGIN_WORKTREE GROK_WORKTREE
# The worktrees must already exist at these exact heads. No fetching, installs,
# builds, source changes, service calls, or guest operations happen here.
set -u
E=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ORIGIN=$(cd -- "${1:?supply the origin worktree}" && pwd)
GROK=$(cd -- "${2:?supply the existing Grok worktree}" && pwd)
PY=${PYTHON:-python3}
test "$(git -C "$ORIGIN" rev-parse HEAD)" = 6dea13a3f1e7a9f26444f7835ebcc53c967ca616 || exit 1
test "$(git -C "$GROK" rev-parse HEAD)" = 8e0214e0251f9a727d70b751aec61a190b017811 || exit 1

CUA_TELEMETRY_ENABLED=false PYTHONDONTWRITEBYTECODE=1 \
QUALIFICATION_SOURCE_ROOT="$ORIGIN" PYTHONPATH="$ORIGIN/libs/python/cua-sandbox" \
  "$PY" "$E/observe.py" > "$E/observed.rerun.log" 2>&1
printf 'observation_exit=%s\n' "$?"

for variant in origin grok; do
  if [ "$variant" = origin ]; then R="$ORIGIN"; else R="$GROK"; fi
  CUA_TELEMETRY_ENABLED=false PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  QUALIFICATION_SOURCE_ROOT="$R" QUALIFICATION_EVIDENCE_DIR="$E" \
  PYTHONPATH="$R/libs/python/cua-sandbox:$E" "$PY" -c \
  'import os; from pathlib import Path; import guards, pytest; import cua_sandbox.runtime.lume as m; e=Path(os.environ["QUALIFICATION_EVIDENCE_DIR"]); print("SOURCE:", Path(m.__file__).resolve().relative_to(Path(os.environ["QUALIFICATION_SOURCE_ROOT"]))); raise SystemExit(pytest.main(["-c", "/dev/null", "-v", "-p", "pytest_asyncio.plugin", "-p", "guards", "-o", "asyncio_mode=auto", "--confcutdir="+str(e), str(e/"grok-source/libs/python/cua-sandbox/tests/test_lume_checkpoint_created_at.py")]))' \
    > "$E/grok-tests-$variant.rerun.log" 2>&1
  printf '%s_exit=%s\n' "$variant" "$?"
done
# Expected: observation_exit=0; origin_exit=1 (2 assertion failures); grok_exit=0 (2 passes).
