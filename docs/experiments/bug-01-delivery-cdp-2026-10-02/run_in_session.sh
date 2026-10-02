#!/usr/bin/env bash
# usage (always via the isolated session, from the worktree root):
#   cua-x11-session.sh <packet>/run_in_session.sh <worktree> <driver-bin> <probe.py> [probe args...]
# Default Driver safety settings: no permission-mode override, no approval
# bypass, Chromium sandbox on. Refuses to run outside the private X11 session.
set -uo pipefail
WT="$1"; DRV="$2"; PROBE="$3"; shift 3
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
export CUA_DRIVER_BIN="$DRV"
PKT="$WT/docs/experiments/bug-01-delivery-cdp-2026-10-02"
cd "$WT/libs/cua-driver/examples/jev-use" || exit 98
echo "== bug01 probe=$PROBE DISPLAY=$DISPLAY lock_note=caller-held"
.venv/bin/python "$PKT/$PROBE" "$@"
rc=$?
echo "rc_probe=$rc"
exit $rc
