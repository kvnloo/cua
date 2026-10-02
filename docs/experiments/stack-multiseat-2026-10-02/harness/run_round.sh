#!/usr/bin/env bash
# run_round.sh <round-dir> <conc|seq> <hermes|direct> <AID:NOTE:K> [<AID:NOTE:K> ...]
# Host-side round driver; run it under hostless (refuses otherwise). Starts one private 1-seat headless sway
# session per agent (cua-sway-session.sh), all at once (conc) or one after another (seq), with a 1 Hz resource
# sampler. Everything an agent touches lives inside its own session; the shared resource is the model server.
# Env knobs: MS_* (see agent_hermes.sh), MS_OLLAMA_PID, MS_SESSION_TIMEOUT, MS_OUTPUTS.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
R="$1"; ARM="$2"; MODE="$3"; shift 3
H="$(cd "$(dirname "$0")" && pwd)"
SESSION="${MS_SESSION_SCRIPT:?MS_SESSION_SCRIPT (cua-sway-session.sh) not set}"
mkdir -p "$R"; [ -e "$R/round.json" ] && { echo "round exists: $R" >&2; exit 2; }
EXTRA="MS_GTK3_MAIN=$MS_GTK3_MAIN MS_VENV_PY=$MS_VENV/bin/python MS_VENV=$MS_VENV MS_HERMES_WT=$MS_HERMES_WT"
EXTRA="$EXTRA MS_TEMPLATE_HOME=$MS_TEMPLATE_HOME MS_CONFIG_TEMPLATE=$MS_CONFIG_TEMPLATE MS_MODEL=$MS_MODEL"
EXTRA="$EXTRA MS_BASE_URL=$MS_BASE_URL MS_MAX_TURNS=${MS_MAX_TURNS:-16} CUA_DRIVER_BIN=$CUA_DRIVER_BIN"
EXTRA="$EXTRA MS_LIVE_HOME=$MS_LIVE_HOME MS_REAL_HOME=$MS_REAL_HOME MS_AGENT_TIMEOUT=${MS_AGENT_TIMEOUT:-900}"
launch() {  # $1 = AID:NOTE:K
  IFS=: read -r aid note k <<< "$1"
  ( cd "$H/../../../.." && CUA_SWAY_SEATS=1 CUA_SWAY_OUTPUTS="${MS_OUTPUTS:-1280x800}" CUA_SESSION_ATSPI=1 \
      CUA_SWAY_TIMEOUT="${MS_SESSION_TIMEOUT:-1200}" CUA_SESSION_EXTRA_ENV="$EXTRA" \
      exec "$SESSION" "$H/agent_session.sh" "$R/$aid" "$aid" "$note" "$k" "$MODE" ) \
    > "$R/$aid.session.log" 2>&1
  echo "$?" > "$R/$aid.session_rc"
}
rm -f "$R/sampler.stop"
python3 "$H/sampler.py" "$R/resources.jsonl" "$$" "$R/sampler.stop" "${MS_OLLAMA_PID:-}" &
SP=$!
t0="$(date +%s.%N)"
if [ "$ARM" = conc ]; then
  pids=(); for spec in "$@"; do launch "$spec" & pids+=($!); done
  wait "${pids[@]}"
else
  for spec in "$@"; do launch "$spec"; done
fi
t1="$(date +%s.%N)"
touch "$R/sampler.stop"; wait "$SP" 2>/dev/null
python3 - "$R" "$ARM" "$MODE" "$t0" "$t1" "$@" <<'PY'
import json, sys
r, arm, mode, t0, t1, *specs = sys.argv[1:]
json.dump({"arm": arm, "mode": mode, "t0": float(t0), "t1": float(t1), "makespan_s": round(float(t1) - float(t0), 3),
           "agents": [dict(zip(("aid", "note", "k"), s.split(":"))) for s in specs]},
          open(f"{r}/round.json", "w"), indent=1)
PY
echo "round $R arm=$ARM mode=$MODE makespan=$(python3 -c "print(round($t1-$t0,1))")s"
