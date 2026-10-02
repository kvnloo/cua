#!/usr/bin/env bash
# run_one.sh: ONE Hermes computer-use task run inside a private X11 session.
# Must be started as:  hostless cua-x11-session.sh run_one.sh   with CUA_SESSION_ATSPI=1 and
#   CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 SMOKE_ENV=<run>/run.env"
# <run>/run.env (written by drive.py, never committed) supplies every path and the run parameters:
#   RUN TASK ARM PROMPT TOKEN DRIVER HERMES_WT HERMES_VENV Z0_WT Z0_VENV FIXTURE_GTK FIXTURE_SERVER
#   SHADOW_BACKEND HERMES_TIMEOUT MAX_TURNS LIVE_HERMES_HOME REAL_HOME HF_HUB_DIR NANOJEV_CKPT JULIA_PY STABLE
# Arms: on = observer plugin + shadow sidecar; off = no observer, no sidecar;
#       offdelay/onnowait = exploratory delay controls (see EXPLORATORY_PREREG.json);
#       outage = observer + sidecar whose backend weights are unavailable (residency miss).
set -uo pipefail
case "${XDG_RUNTIME_DIR:-}" in */x11-session.*/xdg-runtime) ;; *) echo "refusing: not inside the private X11 session" >&2; exit 97;; esac
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: host display variables present" >&2; exit 97; }
# shellcheck disable=SC1090
. "$SMOKE_ENV"
H="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$RUN/meta" "$RUN/fixture" "$RUN/shadow" "$RUN/cwd" "$RUN/tmp"
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

# --- shadow sidecar (separate process; output dir is invisible to Hermes) ---
SC=""
if [ "$ARM" != off ] && [ "$ARM" != offdelay ]; then
  # Private sidecar HOME exposing ONLY the HF model hub (no token files): z0int resolves weights under
  # ~/.cache/huggingface/hub. Outage arm = injected residency miss: the hub link is absent, hub offline.
  SC_HOME="$RUN/tmp/sc-home"; mkdir -p "$SC_HOME/.cache/huggingface"
  [ "$ARM" = outage ] || ln -s "$HF_HUB_DIR" "$SC_HOME/.cache/huggingface/hub"
  env -i PATH="$Z0_VENV/bin:/usr/bin:/bin" HOME="$SC_HOME" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
      HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 \
      TMPDIR="$RUN/tmp" Z0INT_HOME="$RUN/shadow/z0int-home" Z0INT_NANOJEV_CHECKPOINT="$NANOJEV_CKPT" \
      Z0INT_JULIA_PYTHON="$JULIA_PY" Z0INT_LAYA_DEVICE=cpu Z0INT_JULIA_DEVICE=cpu LANG=C.UTF-8 \
    "$Z0_VENV/bin/python" "$H/shadow_sidecar.py" --events "$RUN/home/.hermes/plugin-data/z0-hermes-observer/events.jsonl" \
      --out "$RUN/shadow" --z0int-home "$RUN/shadow/z0int-home" --backend "$SHADOW_BACKEND" \
      --stop-file "$RUN/meta/hermes.done" --hermes-lab "$HERMES_WT/lab/z0_hermes_observer" --z0-wt "$Z0_WT" \
      --arm "$ARM" --warm > "$RUN/shadow/sidecar.log" 2>&1 &
  SC=$!
  if [ "$ARM" != onnowait ]; then  # onnowait (exploratory): Hermes does not wait for the sidecar
    for _ in $(seq 600); do [ -e "$RUN/shadow/sidecar_ready" ] && break; sleep 0.2; done
  fi
  log "sidecar ready=$([ -e "$RUN/shadow/sidecar_ready" ] && echo yes || echo no)"
fi
if [ "$ARM" = offdelay ]; then  # exploratory: no shadow stack, but the same start delay the on arm incurs
  sleep "${START_DELAY:-17.5}"; log "offdelay slept ${START_DELAY:-17.5}s"
fi

# --- Hermes (isolated runtime; live Hermes home, real home, shadow output and fixture state masked) ---
log "hermes start"
date +%s.%N > "$RUN/meta/hermes.start"
# Hermes sees its run home/cwd/tmp at CONSTANT paths ($STABLE/{home,cwd,tmp}, bind mounts inside its own
# sandbox), so the system prompt (which names home, cwd and scratch dirs) is byte-identical across runs.
W="$STABLE"
timeout --kill-after=10 "$HERMES_TIMEOUT" bwrap --dev-bind / / \
    --tmpfs "$LIVE_HERMES_HOME" --tmpfs "$REAL_HOME" --tmpfs "$RUN/shadow" --tmpfs "$RUN/fixture" \
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
      echo "shadow_dir_entries=$(ls -A "$4" | wc -l)"; echo "fixture_dir_entries=$(ls -A "$5" | wc -l)"; } > "$meta/mask.inside"
    env | sort | sed "s|=.*/x11-session\.|=<session>/x11-session.|" > "$meta/env.inside"
    shift 5
    exec "$VIRTUAL_ENV/bin/python" -m hermes_cli.main chat -Q -t computer_use --max-turns "$1" -q "$2"
  ' _ "$RUN/meta" "$LIVE_HERMES_HOME" "$REAL_HOME" "$RUN/shadow" "$RUN/fixture" "$MAX_TURNS" "$PROMPT" \
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

# --- stop the sidecar after it drained the spool ---
touch "$RUN/meta/hermes.done"
if [ -n "$SC" ]; then
  for _ in $(seq 600); do kill -0 "$SC" 2>/dev/null || break; sleep 0.2; done
  kill "$SC" 2>/dev/null && log "sidecar killed after drain timeout"
  wait "$SC" 2>/dev/null; echo "$?" > "$RUN/shadow/sidecar_rc"
fi
for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
wait 2>/dev/null
snap > "$RUN/meta/live-home-stat.after"
log "session end"
exit 0
