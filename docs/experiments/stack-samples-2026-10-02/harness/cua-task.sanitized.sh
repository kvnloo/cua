#!/usr/bin/env bash
# cua-task.sh <run-id> <density|none> <max-turns> <prompt>
# Runs inside a private X11 session (cua-x11-session.sh under hostless, CUA_HOSTLESS=1, private AT-SPI).
# Starts the canonical GTK3 TaskWindow fixture with an app-owned state file (the oracle input),
# runs one Hermes computer_use turn through run-hermes.sh, then snapshots the state file.
set -uo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] && [ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "cua-task: refusing: not inside a hostless private X11 session" >&2; exit 97; }
run_id="$1"; density="$2"; turns="$3"; prompt="$4"
LANE=$LANE_DIR
FIX=$CUA_WT/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py
STATE_DIR="$LANE/gui-state/$run_id"; mkdir -p "$STATE_DIR"; STATE="$STATE_DIR/task-state.json"
if [ "$density" = none ]; then
  CUA_GTK3_TASK_STATE="$STATE" /usr/bin/python3 "$FIX" > "$STATE_DIR/fixture.log" 2>&1 &
else
  CUA_GTK3_TASK_STATE="$STATE" CUA_GTK3_TASK_DENSITY="$density" /usr/bin/python3 "$FIX" > "$STATE_DIR/fixture.log" 2>&1 &
fi
GPID=$!
for _ in $(seq 1 50); do [ -s "$STATE" ] && break; sleep 0.2; done
cp "$STATE" "$STATE_DIR/state.before.json" 2>/dev/null
sleep 1
STACK_GUI=1 STACK_EXTRA_ENV="DISPLAY=$DISPLAY DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-} ${AT_SPI_BUS_ADDRESS:+AT_SPI_BUS_ADDRESS=$AT_SPI_BUS_ADDRESS}" \
  "$LANE/run-hermes.sh" "$run_id" -m hermes_cli.main chat -Q -t computer_use --max-turns "$turns" -q "$prompt"
rc=$?
cp "$STATE" "$STATE_DIR/state.after.json" 2>/dev/null
kill "$GPID" 2>/dev/null; wait "$GPID" 2>/dev/null
cp -a "$STATE_DIR" "$LANE/runs/$run_id/meta/gui-state" 2>/dev/null
exit $rc
