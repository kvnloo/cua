#!/usr/bin/env bash
# usage: run_reps.sh <examples-dir> <driver> <out-dir> <N>   (inside cua-x11-session.sh)
set -uo pipefail
EX="$1"; DRV="$2"; OUT="$3"; N="$4"; HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CUA_DRIVER_PERMISSION_MODE=unrestricted CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1
fail=0
for i in $(seq 1 "$N"); do
  R="$OUT/run$(printf '%02d' "$i")"; mkdir -p "$R"
  printf '#!/bin/bash\nexport CUA_E2E_BROWSER_NO_SANDBOX=1\nexport CUA_E2E_BROWSER_STDERR=1\nexec %s "$@"\n' "$DRV" > "$R/driver.sh"; chmod 700 "$R/driver.sh"
  CUA_DRIVER_BIN="$R/driver.sh" "$EX/.venv/bin/python" "$HERE/guarded_cross_session.py" --examples-dir "$EX" --out "$R/result.json" > "$R/stdout.txt" 2> "$R/stderr.txt"
  rc=$?; echo "{\"run\": $i, \"rc\": $rc}"; [ $rc -ne 0 ] && fail=$((fail+1))
done
echo "{\"repetitions\": $N, \"failures\": $fail}"
