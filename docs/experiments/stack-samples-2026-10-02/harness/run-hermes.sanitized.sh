#!/usr/bin/env bash
# run-hermes.sh <run-id> <python args...>   (stack SAMPLES lane; derived from the stack-integration launcher)
# Runs the stack-samples Hermes worktree from its dedicated venv in a fresh private run dir:
#   - hostless (host X11/Wayland/D-Bus/AT-SPI masked, desktop env stripped). When already inside a
#     private session (CUA_HOSTLESS=1, e.g. cua-x11-session.sh under hostless) it is not re-applied,
#     so the session's own abstract sockets stay in the same Landlock domain.
#   - nested bwrap masks the live Hermes home ($LIVE_HERMES_HOME) and the real $HOME with tmpfs
#   - env -i allow-list: no inherited HERMES_HOME, API keys or tokens; HOME/HERMES_HOME/TMPDIR/XDG_*
#     inside the run dir; HTTP(S) egress proxied to a dead port except loopback
#   - STACK_RUN_TIMEOUT (default 420 s) bounds one run; STACK_EXTRA_ENV adds K=V pairs (GUI session vars)
set -euo pipefail
LANE=$LANE_DIR
WT=$HERMES_WT
VENV=$HERMES_VENV
DRIVER="${STACK_CUA_DRIVER:-$CUA_DRIVER}"
HOSTLESS=$HOSTLESS
REAL_HOME_MASK=$REAL_HOME
LIVE_HERMES_HOME=$LIVE_HERMES_HOME

run_id="$1"; shift
RUN="$LANE/runs/$run_id"
[ -e "$RUN" ] && { echo "run dir exists: $RUN" >&2; exit 2; }
mkdir -p "$RUN"
cp -a "$LANE/template/home" "$RUN/home"
mkdir -p "$RUN/tmp" "$RUN/cwd" "$RUN/meta" "$RUN/xdg" "$RUN/home/.config" "$RUN/home/.cache" \
         "$RUN/home/.local/share" "$RUN/home/.local/state"
chmod 700 "$RUN/xdg"
[ -d "${STACK_FIXTURE_DIR:-/nonexistent}" ] && cp -a "$STACK_FIXTURE_DIR/." "$RUN/cwd/"

snap() { for p in "$LIVE_HERMES_HOME" "$LIVE_HERMES_HOME/state.db" "$LIVE_HERMES_HOME/state.db-wal" \
                  "$LIVE_HERMES_HOME/config.yaml" "$LIVE_HERMES_HOME/.env" "$LIVE_HERMES_HOME/auth.json" \
                  "$LIVE_HERMES_HOME/logs"; do
           stat -c '%n|%y|%s' "$p" 2>/dev/null || echo "$p|absent"; done; }
snap > "$RUN/meta/live-home-stat.before"
git -C "$WT" rev-parse HEAD > "$RUN/meta/worktree-head"
git -C "$WT" status --porcelain > "$RUN/meta/worktree-status"
printf '%s\n' "$@" > "$RUN/meta/argv"
date -u +%FT%T.%3NZ > "$RUN/meta/started_at"

if [ "${CUA_HOSTLESS:-}" = 1 ]; then OUTER=(); else OUTER=("$HOSTLESS"); fi
# hostless v2 leaves path sockets visible: mask the host runtime dir always, and the host X11 socket
# dir unless this is a GUI run inside a private X session (STACK_GUI=1 keeps its own display socket).
MASKS=(--tmpfs "/run/user/$(id -u)" --tmpfs /tmp/.X11-unix)
if [ "${STACK_GUI:-0}" = 1 ]; then
  dnum="${DISPLAY#:}"; dnum="${dnum%%.*}"
  [ -S "/tmp/.X11-unix/X$dnum" ] || { echo "run-hermes: private display socket X$dnum missing" >&2; exit 96; }
  MASKS+=(--bind "/tmp/.X11-unix/X$dnum" "/tmp/.X11-unix/X$dnum")
fi
set +e
"${OUTER[@]}" bwrap --dev-bind / / \
    --tmpfs "$LIVE_HERMES_HOME" --tmpfs "$REAL_HOME_MASK" "${MASKS[@]}" \
    --chdir "$RUN/cwd" --die-with-parent -- \
  env -i \
    PATH="$VENV/bin:/usr/local/bin:/usr/bin:/bin" \
    VIRTUAL_ENV="$VENV" \
    HOME="$RUN/home" \
    HERMES_HOME="$RUN/home/.hermes" \
    TMPDIR="$RUN/tmp" \
    XDG_RUNTIME_DIR="$RUN/xdg" \
    XDG_CONFIG_HOME="$RUN/home/.config" XDG_CACHE_HOME="$RUN/home/.cache" \
    XDG_DATA_HOME="$RUN/home/.local/share" XDG_STATE_HOME="$RUN/home/.local/state" \
    LANG=C.UTF-8 TZ=UTC TERM=dumb NO_COLOR=1 PYTHONUNBUFFERED=1 \
    CUA_HOSTLESS=1 \
    HERMES_CUA_DRIVER_CMD="$DRIVER" \
    CUA_DRIVER_RS_TELEMETRY_ENABLED=0 \
    HERMES_API_TIMEOUT="${STACK_API_TIMEOUT:-600}" \
    HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 \
    http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9 \
    NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
    ${STACK_EXTRA_ENV:-} \
  bash -c '
    meta="$1"; to="$2"; shift 2
    env | sort > "$meta/env.inside"
    { echo "live_hermes_home_entries=$(ls -A '"$LIVE_HERMES_HOME"' | wc -l)";
      echo "real_home_entries=$(ls -A '"$REAL_HOME_MASK"' | wc -l)";
      echo "run_user_entries=$(ls -A /run/user/$(id -u) 2>/dev/null | wc -l)";
      echo "x11_entries=$(ls -A /tmp/.X11-unix 2>/dev/null | tr "\n" " ")"; } > "$meta/mask.inside"
    exec timeout --kill-after=15 "$to" "$VIRTUAL_ENV/bin/python" "$@"
  ' _ "$RUN/meta" "${STACK_RUN_TIMEOUT:-420}" "$@" > "$RUN/meta/stdout" 2> "$RUN/meta/stderr"
rc=$?
set -e
date -u +%FT%T.%3NZ > "$RUN/meta/ended_at"
echo "$rc" > "$RUN/meta/exit_code"
snap > "$RUN/meta/live-home-stat.after"
echo "run=$RUN rc=$rc"
exit "$rc"
