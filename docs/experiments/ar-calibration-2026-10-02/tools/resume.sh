#!/usr/bin/env bash
# Detached continuation of run_all.sh (survives the 2 h limit of the agent's background task).
# Waits for the earlier run_all.sh to exit; an evaluation it left unfinished (no final.json) is moved
# aside, never mixed with a re-run; then continues the pre-registered order.
cd <tmp>/ar-calib
while pgrep -f '^bash tools/run_all.sh' > /dev/null; do sleep 15; done
mkdir -p evals-interrupted
for d in evals/*; do [ -f "$d/final.json" ] || { mv "$d" "evals-interrupted/$(basename "$d")-$(date +%s)"; echo "moved unfinished $d" >> run_all.log; }; done
exec <tmp>/ar-calib/tools/run_all.sh
