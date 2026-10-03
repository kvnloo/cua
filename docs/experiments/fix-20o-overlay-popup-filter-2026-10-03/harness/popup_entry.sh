#!/usr/bin/env bash
# usage (inside hostless + hostless-strict + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   popup_entry.sh <worktree> <plan.json> <block> <label> <raw-out-dir> <work-dir> NAME=BIN:SHA256 ...
# Same trust checks as the original OWN-20P session_entry.sh (exit 97 = display not answering, nothing
# ran, the orchestrator starts a new session), then the packet's popup_harness.py with the jev-use venv.
set -uo pipefail
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 96; }
case "${XDG_RUNTIME_DIR:-}" in /run/user/*) echo "refusing: host runtime dir" >&2; exit 96 ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) echo "refusing: host session bus" >&2; exit 96 ;; esac
xdpyinfo >/dev/null 2>&1 || { echo "[session] xdpyinfo probe failed" >&2; exit 97; }
WT="$1"; PLAN="$2"; BLOCK="$3"; LABEL="$4"; OUT="$5"; WORK="$6"; shift 6
HERE="$(cd "$(dirname "$0")" && pwd)"
for spec in "$@"; do
  b="${spec#*=}"; echo "[session] version ${spec%%=*}: $("${b%:*}" --version 2>&1 | head -1)" >&2
done
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/popup_harness.py" \
  --wt "$WT" --plan "$PLAN" --block "$BLOCK" --label "$LABEL" --out "$OUT" --work "$WORK" "$@"
