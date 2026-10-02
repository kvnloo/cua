#!/usr/bin/env bash
# collect.sh <tasks.jsonl> <fixtures_dir> <out_dir> <deadline_utc ISO8601>
# Runs every frozen task in its preregistered order, one at a time, until done or until the deadline
# (no new task starts after it; tasks not started are NOT_RUN). Must run under hostless.
# Per task: one isolated Hermes process (run-hermes.sh; CUA tasks inside a fresh private X11 session
# via cua-task.sh), then the independent fixture oracle. Appends index.jsonl and verdicts.jsonl.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "collect: run under hostless" >&2; exit 97; }
TASKS="$1"; FIX="$2"; OUT="$3"; DEADLINE="$4"
LANE="${STACK_LANE_DIR:?set STACK_LANE_DIR (private lane tmp with run-hermes.sh, cua-task.sh, runs/)}"
SESSION="${STACK_X11_SESSION:?set STACK_X11_SESSION (cua-x11-session.sh)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${STACK_RUN_PREFIX:-S}"
mkdir -p "$OUT"
deadline_s=$(date -u -d "$DEADLINE" +%s)
python3 - "$TASKS" > "$OUT/.order" <<'PY'
import json, sys
for line in open(sys.argv[1]):
    if line.strip():
        t = json.loads(line)
        print("\t".join([t["task_id"], t["kind"], t.get("density", "none"), str(t["max_turns"]), t["prompt"]]))
PY
while IFS=$'\t' read -r task_id kind density turns prompt; do
  run_id="$PREFIX-$task_id"
  if grep -q "\"task_id\": \"$task_id\"" "$OUT/index.jsonl" 2>/dev/null; then continue; fi
  if [ "$(date -u +%s)" -ge "$deadline_s" ]; then
    printf '{"task_id": "%s", "status": "NOT_RUN", "reason": "deadline"}\n' "$task_id" >> "$OUT/index.jsonl"; continue
  fi
  t0=$(date -u +%FT%T.%3NZ)
  if [ "$kind" = file ]; then
    STACK_FIXTURE_DIR="$FIX/$task_id" "$LANE/run-hermes.sh" "$run_id" -m hermes_cli.main chat -Q -t file \
      --max-turns "$turns" -q "$prompt" > "$OUT/.last" 2>&1 < /dev/null
    rc=$?
  else
    ( cd "$LANE" && CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 CUA_HOSTLESS=1" \
        "$SESSION" "$LANE/cua-task.sh" "$run_id" "$density" "$turns" "$prompt" ) > "$OUT/.last" 2>&1 < /dev/null
    rc=$?
  fi
  t1=$(date -u +%FT%T.%3NZ)
  run_dir="$LANE/runs/$run_id"
  sid=$(cat "$run_dir/meta/stdout" "$run_dir/meta/stderr" 2>/dev/null | grep -m1 '^session_id:' | awk '{print $2}')
  python3 "$HERE/workload.py" oracle "$TASKS" "$run_dir" "$task_id" < /dev/null >> "$OUT/verdicts.jsonl" \
    || printf '{"task_id": "%s", "verified_success": null, "oracle_error": true}\n' "$task_id" >> "$OUT/verdicts.jsonl"
  printf '{"task_id": "%s", "run_id": "%s", "kind": "%s", "status": "RUN", "exit_code": %d, "session_id": "%s", "started_at": "%s", "ended_at": "%s"}\n' \
    "$task_id" "$run_id" "$kind" "$rc" "${sid:-}" "$t0" "$t1" >> "$OUT/index.jsonl"
done < "$OUT/.order"
echo "collect: done $(date -u +%FT%TZ)"
