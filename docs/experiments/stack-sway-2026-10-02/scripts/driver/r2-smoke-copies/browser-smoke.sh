#!/usr/bin/env bash
# usage (always via the isolated session):
#   cua-x11-session.sh <lanes>/artifacts/r2/smoke/browser-smoke.sh <worktree> <driver-bin-or-wrapper> <outdir>
# Runs the existing jev-use checks (no new harness): MCP initialize + tools/list, then
# verify_setup.py (mock provider): browser_prepare isolated_new profile -> navigate loopback fixture ->
# browser_type + browser_click (DOM page-structure path) -> independent fixture /state oracle.
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
mkdir -p "$(dirname "$OUT")"
export CUA_DRIVER_BIN="$DRV"
# Default Driver safety settings: no permission-mode override, no approval bypass, Chromium sandbox on.
cd "$WT/libs/cua-driver/examples/jev-use"
echo "== env DISPLAY=$DISPLAY HOME=$HOME XDG_STATE_HOME=$XDG_STATE_HOME"
echo "== verify_mcp_tools"; .venv/bin/python verify_mcp_tools.py; echo "rc_mcp_tools=$?"
echo "== verify_setup (mock, python)"; .venv/bin/python verify_setup.py --output-dir "$OUT"; echo "rc_verify_setup=$?"
