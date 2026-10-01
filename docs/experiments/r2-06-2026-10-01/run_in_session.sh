#!/usr/bin/env bash
# usage (always via the isolated session, from the worktree root):
#   cua-x11-session.sh <packet>/run_in_session.sh <worktree> <driver-bin> <plan.json> <outdir> <driver-label> [extra probe args]
# Default Driver safety settings: no permission-mode override, no approval
# bypass, Chromium sandbox on. Refuses to run outside the private X11 session.
set -uo pipefail
WT="$1"; DRV="$2"; PLAN="$3"; OUT="$4"; LABEL="$5"; shift 5
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
export CUA_DRIVER_BIN="$DRV"
PKT="$WT/docs/experiments/r2-06-2026-10-01"
cd "$WT/libs/cua-driver/examples/jev-use" || exit 98
echo "== r2-06 probe label=$LABEL DISPLAY=$DISPLAY"
.venv/bin/python "$PKT/probe_trusted_input.py" --plan "$PLAN" --out "$OUT" --driver-label "$LABEL" "$@"
rc=$?
echo "rc_probe=$rc"
exit $rc
