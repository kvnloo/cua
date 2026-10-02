#!/usr/bin/env bash
# usage (inside cua-x11-session.sh with CUA_SESSION_ATSPI=1 + CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1",
# itself under the hostless wrapper):
#   run_in_session.sh <worktree> <script.py> [args...]
# Runs a fixture script with the worktree's jev-use venv, refusing outside a private X11 session.
set -uo pipefail
WT="$1"; SCRIPT="$2"; shift 2
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$WT/docs/experiments/ar-harness-2026-10-02/fixtures/$SCRIPT" "$@"
