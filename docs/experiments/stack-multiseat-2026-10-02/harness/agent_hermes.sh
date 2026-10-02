#!/usr/bin/env bash
# agent_hermes.sh <agent-dir> <prompt-file>     (inside a private sway session; one Hermes agent)
# Runs the lane Hermes worktree from its dedicated venv with HOME/HERMES_HOME inside <agent-dir>, in a nested
# bwrap that hides the live Hermes home and the real home, from an env -i allow-list. The Driver is spawned by
# Hermes (HERMES_CUA_DRIVER_CMD) and sees only this session's DISPLAY / D-Bus / AT-SPI.
# Knobs (from the session env): MS_HERMES_WT, MS_VENV, MS_TEMPLATE_HOME, MS_CONFIG_TEMPLATE, MS_MODEL,
#   MS_BASE_URL, MS_MAX_TURNS, CUA_DRIVER_BIN, MS_LIVE_HOME, MS_REAL_HOME.
set -uo pipefail
case "${CUA_SWAY_RUN:-}" in */sway-session.*) ;; *) echo "refusing: not in a private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
A="$1"; PROMPT_FILE="$2"
mkdir -p "$A/meta" "$A/tmp" "$A/cwd"
cp -a "${MS_TEMPLATE_HOME:?}" "$A/home"
mkdir -p "$A/home/.config" "$A/home/.cache" "$A/home/.local/share" "$A/home/.local/state"
sed -e "s#@MODEL@#${MS_MODEL:?}#" -e "s#@BASE_URL@#${MS_BASE_URL:?}#" "${MS_CONFIG_TEMPLATE:?}" > "$A/home/.hermes/config.yaml"
git -C "${MS_HERMES_WT:?}" rev-parse HEAD > "$A/meta/worktree-head"
git -C "$MS_HERMES_WT" status --porcelain > "$A/meta/worktree-status"
date -u +%FT%T.%3NZ > "$A/meta/start"
date +%s.%N > "$A/meta/start_epoch"
set +e
bwrap --dev-bind / / --tmpfs "${MS_LIVE_HOME:?}" --tmpfs "${MS_REAL_HOME:?}" --chdir "$A/cwd" --die-with-parent -- \
  env -i \
    PATH="$MS_VENV/bin:/usr/local/bin:/usr/bin:/bin" VIRTUAL_ENV="$MS_VENV" \
    HOME="$A/home" HERMES_HOME="$A/home/.hermes" TMPDIR="$A/tmp" \
    XDG_CONFIG_HOME="$A/home/.config" XDG_CACHE_HOME="$A/home/.cache" \
    XDG_DATA_HOME="$A/home/.local/share" XDG_STATE_HOME="$A/home/.local/state" \
    XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" DISPLAY="$DISPLAY" DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
    XDG_SESSION_TYPE=x11 \
    LANG=C.UTF-8 TZ=UTC TERM=dumb NO_COLOR=1 PYTHONUNBUFFERED=1 CUA_HOSTLESS=1 \
    HERMES_CUA_DRIVER_CMD="${CUA_DRIVER_BIN:?}" CUA_DRIVER_RS_TELEMETRY_ENABLED=0 \
    HERMES_API_TIMEOUT=900 \
    HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
    http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9 \
    NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  bash -c '
    meta="$1"; live="$2"; real="$3"; shift 3
    env | sort > "$meta/env.inside"
    { echo "live_hermes_home_entries=$(ls -A "$live" | wc -l)"; echo "real_home_entries=$(ls -A "$real" | wc -l)"
      echo "x11_entries=$(ls -A /tmp/.X11-unix | tr "\n" " ")"; } > "$meta/mask.inside"
    exec "$VIRTUAL_ENV/bin/python" "$@"
  ' _ "$A/meta" "$MS_LIVE_HOME" "$MS_REAL_HOME" -m hermes_cli.main chat -Q -t computer_use --max-turns "${MS_MAX_TURNS:-16}" -q "$(cat "$PROMPT_FILE")" \
  > "$A/meta/stdout" 2> "$A/meta/stderr"
rc=$?
set -e
date +%s.%N > "$A/meta/end_epoch"
echo "$rc" > "$A/meta/exit_code"
exit "$rc"
