#!/usr/bin/env bash
# run_one.sh: ONE Hermes computer-use task run inside a private X11 session (stack2-addr).
# Adapted from the accepted SMOKE run_one.sh: same fixtures, Hermes sandbox, env allow-list and oracle; no shadow
# sidecar. Must be started as:  hostless cua-x11-session.sh run_one.sh   with CUA_SESSION_ATSPI=1 and
#   CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 SMOKE_ENV=<run>/run.env"
# <run>/run.env (written by drive.py, never committed) supplies every path and the run parameters:
#   RUN TASK ARM PROMPT TOKEN DRIVER HERMES_WT HERMES_VENV FIXTURE_GTK FIXTURE_SERVER HERMES_TIMEOUT MAX_TURNS
#   LIVE_HERMES_HOME REAL_HOME STABLE
set -uo pipefail
case "${XDG_RUNTIME_DIR:-}" in */x11-session.*/xdg-runtime) ;; *) echo "refusing: not inside the private X11 session" >&2; exit 97;; esac
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: host display variables present" >&2; exit 97; }
# shellcheck disable=SC1090
. "$SMOKE_ENV"
H="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$RUN/meta" "$RUN/fixture" "$RUN/cwd" "$RUN/tmp"
log() { printf '%s %s\n' "$(date -u +%FT%T.%3NZ)" "$*" >> "$RUN/meta/timeline.log"; }
snap() { for p in "$LIVE_HERMES_HOME" "$LIVE_HERMES_HOME/state.db" "$LIVE_HERMES_HOME/state.db-wal" \
                  "$LIVE_HERMES_HOME/config.yaml" "$LIVE_HERMES_HOME/.env" "$LIVE_HERMES_HOME/auth.json" \
                  "$LIVE_HERMES_HOME/logs"; do stat -c '%n|%y|%s' "$p" 2>/dev/null || echo "$p|absent"; done; }
snap > "$RUN/meta/live-home-stat.before"
env | grep -E '^(DISPLAY|XDG_SESSION_TYPE|XDG_RUNTIME_DIR|HOME|WAYLAND_DISPLAY|HYPRLAND_INSTANCE_SIGNATURE|CUA_HOSTLESS)=' \
  | sed "s|=.*/x11-session\.|=<session>/x11-session.|" | sort > "$RUN/meta/session.env"
log "session start task=$TASK arm=$ARM"

# --- fixture (app-owned state; the oracle never asks Hermes, the observer or the Driver) ---
PIDS=()
if [ "$TASK" = gtk3 ]; then
  CUA_GTK3_TASK_STATE="$RUN/fixture/gtk3-state.json" /usr/bin/python3 "$FIXTURE_GTK" > "$RUN/fixture/app.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 50); do [ -s "$RUN/fixture/gtk3-state.json" ] && break; sleep 0.2; done
  cp "$RUN/fixture/gtk3-state.json" "$RUN/fixture/state.before.json"
else
  /usr/bin/python3 "$H/fixture_serve.py" "$FIXTURE_SERVER" "$RUN/fixture/port" > "$RUN/fixture/server.log" 2>&1 &
  PIDS+=($!)
  for _ in $(seq 50); do [ -s "$RUN/fixture/port" ] && break; sleep 0.1; done
  PORT="$(cat "$RUN/fixture/port")"
  curl -s --noproxy '*' "http://127.0.0.1:$PORT/state" > "$RUN/fixture/state.before.json"
  ACCESSIBILITY_ENABLED=1 /opt/google/chrome/chrome --user-data-dir="$RUN/tmp/chrome-profile" --no-first-run \
    --no-default-browser-check --disable-sync --password-store=basic --disable-background-networking \
    --disable-component-update --no-pings --proxy-server=http://127.0.0.1:9 --force-renderer-accessibility \
    --window-size=1100,800 --app="http://127.0.0.1:$PORT/" > "$RUN/fixture/chrome.log" 2>&1 &
  PIDS+=($!)
  sleep 4
  dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus org.freedesktop.DBus.Properties.Set \
    string:org.a11y.Status string:IsEnabled variant:boolean:true > /dev/null 2>&1
  sleep 4
fi
log "fixture ready"

# --- Hermes (isolated runtime; live Hermes home, real home and fixture state masked) ---
log "hermes start"
date +%s.%N > "$RUN/meta/hermes.start"
W="$STABLE"
timeout --kill-after=10 "$HERMES_TIMEOUT" bwrap --dev-bind / / \
    --tmpfs "$LIVE_HERMES_HOME" --tmpfs "$REAL_HOME" --tmpfs "$RUN/fixture" \
    --bind "$RUN/home" "$W/home" --bind "$RUN/cwd" "$W/cwd" --bind "$RUN/tmp" "$W/tmp" \
    --chdir "$W/cwd" --die-with-parent -- \
  env -i \
    PATH="$HERMES_VENV/bin:/usr/local/bin:/usr/bin:/bin" VIRTUAL_ENV="$HERMES_VENV" \
    HOME="$W/home" HERMES_HOME="$W/home/.hermes" TMPDIR="$W/tmp" \
    XDG_CONFIG_HOME="$W/home/.config" XDG_CACHE_HOME="$W/home/.cache" \
    XDG_DATA_HOME="$W/home/.local/share" XDG_STATE_HOME="$W/home/.local/state" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" XDG_SESSION_TYPE=x11 DISPLAY="$DISPLAY" \
    DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
    LANG=C.UTF-8 TZ=UTC TERM=dumb NO_COLOR=1 PYTHONUNBUFFERED=1 CUA_HOSTLESS=1 \
    HERMES_CUA_DRIVER_CMD="$DRIVER" CUA_DRIVER_RS_TELEMETRY_ENABLED=0 HERMES_API_TIMEOUT=600 \
    HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
    http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9 \
    NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  bash -c '
    meta="$1"
    { echo "live_hermes_home_entries=$(ls -A "$2" | wc -l)"; echo "real_home_entries=$(ls -A "$3" | wc -l)";
      echo "fixture_dir_entries=$(ls -A "$4" | wc -l)"; } > "$meta/mask.inside"
    env | sort | sed "s|=.*/x11-session\.|=<session>/x11-session.|" > "$meta/env.inside"
    shift 4
    exec "$VIRTUAL_ENV/bin/python" -m hermes_cli.main chat -Q -t computer_use --max-turns "$1" -q "$2"
  ' _ "$RUN/meta" "$LIVE_HERMES_HOME" "$REAL_HOME" "$RUN/fixture" "$MAX_TURNS" "$PROMPT" \
  > "$RUN/meta/stdout" 2> "$RUN/meta/stderr"
rc=$?
date +%s.%N > "$RUN/meta/hermes.end"
echo "$rc" > "$RUN/meta/exit_code"
log "hermes end rc=$rc"

# --- independent oracle: fixture-owned state, read by this harness after Hermes exited ---
if [ "$TASK" = gtk3 ]; then
  cp "$RUN/fixture/gtk3-state.json" "$RUN/fixture/state.after.json"
else
  curl -s --noproxy '*' "http://127.0.0.1:$PORT/state" > "$RUN/fixture/state.after.json"
fi
/usr/bin/python3 "$H/oracle.py" "$TASK" "$TOKEN" "$RUN/fixture/state.before.json" "$RUN/fixture/state.after.json" \
  > "$RUN/oracle.json"
log "oracle $(cat "$RUN/oracle.json")"
for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
wait 2>/dev/null
snap > "$RUN/meta/live-home-stat.after"
log "session end"
exit 0
