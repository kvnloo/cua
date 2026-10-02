#!/usr/bin/env bash
# agent_session.sh <outdir> <agent-id> <note> <increments> [hermes|direct]
# Payload of ONE private sway session (cua-sway-session.sh, 1 seat): one journaled fixture instance + one agent.
#   hermes (default): Hermes + computer_use + cua-driver (spawned by Hermes) does the fixture task.
#   direct:           the scripted Driver client does it (model-free plumbing / controls).
# Records session identity (DISPLAY, sway pid/socket names, X display listeners), sway tree/seats before and
# after, a screenshot, the fixture journal and final state. Never reads anything outside its own session.
set -uo pipefail
case "${CUA_SWAY_RUN:-}" in */sway-session.*) ;; *) echo "refusing: not in a private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
OUT="$1"; AID="$2"; NOTE="$3"; INC="$4"; MODE="${5:-hermes}"
H="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
{ echo "agent=$AID"; echo "display=$DISPLAY"; echo "wayland=$WAYLAND_DISPLAY"; echo "swaysock_name=$(basename "$SWAYSOCK")"
  echo "session_run=$(basename "$CUA_SWAY_RUN")"; echo "pidns_pid1=$(cat /proc/1/comm)"
  echo "x11_dir=$(ls -A /tmp/.X11-unix | tr '\n' ' ')"; } > "$OUT/session.txt"
date +%s.%N > "$OUT/session_ready_epoch"
read -r FP CON < <("$H/fixture_up.sh" "$OUT/journal.jsonl" "$AID")
echo "fixture_pid=$FP sway_con=$CON" >> "$OUT/session.txt"
sleep 0.5
swaymsg -t get_tree -r > "$OUT/tree-before.json"
swaymsg -t get_seats -r > "$OUT/seats-before.json"
cat > "$OUT/prompt.txt" <<EOF
You are operating a Linux desktop through the computer_use tool. The only application window is titled "CuaTestHarness GTK3 Tasks". Your task in that window: put the text $NOTE into the "Note" text field and click the "Save note" button once.
Follow these steps, one computer_use call per step:
Step 1. action="list_windows". Remember the window's pid and window_id; pass both on every later call.
Step 2. action="capture", mode="ax". Read the bounds [x, y, width, height] of "Note" and of "Save note". The click point of an element with bounds [x, y, w, h] is [x + 10, y + 10]; for example the click point of [100, 40, 60, 20] is [110, 50].
Step 3. action="click", coordinate=<click point of "Note">, delivery_mode="foreground".
Step 4. action="type", text="$NOTE", delivery_mode="foreground".
Step 5. action="click", coordinate=<click point of "Save note">, delivery_mode="foreground". Click it only once.
Step 6. action="capture", mode="ax" to check the result.
Never pass the element argument (element-index clicks are not available here). Do not touch any other control. When the steps are done, reply with the single word DONE.
EOF
date +%s.%N > "$OUT/agent_start_epoch"
if [ "$MODE" = direct ]; then
  "${MS_VENV_PY:?}" "$H/driver_direct.py" fill "$OUT/driver.json" "$FP" "$NOTE" "$INC" --session "$AID" \
    > "$OUT/driver.stdout" 2> "$OUT/driver.stderr"; arc=$?
else
  timeout --kill-after=10 "${MS_AGENT_TIMEOUT:-900}" "$H/agent_hermes.sh" "$OUT/hermes" "$OUT/prompt.txt"; arc=$?
fi
date +%s.%N > "$OUT/agent_end_epoch"
echo "$arc" > "$OUT/agent_rc"
sleep 1
swaymsg -t get_tree -r > "$OUT/tree-after.json"
swaymsg -t get_seats -r > "$OUT/seats-after.json"
grim "$OUT/screen-after.png" 2>/dev/null
kill "$FP" 2>/dev/null; wait "$FP" 2>/dev/null
cp "$OUT/journal.jsonl.state.json" "$OUT/final-state.json" 2>/dev/null
exit 0
