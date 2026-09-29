#!/usr/bin/env bash
# Repeat trycua/cua#4317's real two-session Driver/MCP/Chromium isolation proof N times.
# usage (inside the isolated X session, see cua-x11-session.sh):
#   run_isolation.sh <examples-dir> <driver-binary> <out-dir> <N> <mode>
#   mode=witness : python isolation_witness.py (script unmodified, PYTHONPATH=python, server-side journal + MCP trace)
#   mode=ci      : exactly the CI invocation: uv run --frozen python verify_session_isolation.py --output <file>
set -uo pipefail
EX="$1"; DRIVER="$2"; OUT="$3"; N="$4"; MODE="${5:-witness}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$OUT"
export CUA_DRIVER_PERMISSION_MODE=unrestricted CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1
fail=0
for i in $(seq 1 "$N"); do
  RUN="$OUT/run$(printf '%02d' "$i")"; mkdir -p "$RUN"
  if [ "$MODE" = "witness" ]; then
    cat > "$RUN/driver.sh" <<EOF
#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec /usr/bin/python3 "$HERE/../issue-10-4316-ab/mcp_trace_proxy.py" --real "$DRIVER" --trace "$RUN/mcp-trace.jsonl" -- "\$@"
EOF
  else
    cat > "$RUN/driver.sh" <<EOF
#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec "$DRIVER" "\$@"
EOF
  fi
  chmod 700 "$RUN/driver.sh"
  export CUA_DRIVER_BIN="$RUN/driver.sh"
  t0=$(date +%s%N)
  if [ "$MODE" = "witness" ]; then
    (cd "$EX" && "$EX/.venv/bin/python" "$HERE/isolation_witness.py" --examples-dir "$EX" \
        --summary-out "$RUN/summary.json" --witness-out "$RUN/witness.json") > "$RUN/stdout.txt" 2> "$RUN/stderr.txt"
    rc=$?
  else
    (cd "$EX" && uv run --frozen python verify_session_isolation.py --output "$RUN/summary.json") > "$RUN/stdout.txt" 2> "$RUN/stderr.txt"
    rc=$?
  fi
  t1=$(date +%s%N)
  echo "{\"run\": $i, \"mode\": \"$MODE\", \"rc\": $rc, \"wall_ms\": $(( (t1 - t0) / 1000000 ))}" | tee -a "$OUT/runs.jsonl"
  [ "$rc" -ne 0 ] && fail=$((fail + 1))
  sleep 0.5
done
echo "{\"repetitions\": $N, \"failures\": $fail}" | tee "$OUT/overall.json"
exit "$fail"
