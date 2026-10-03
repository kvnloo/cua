#!/usr/bin/env bash
# usage (always via bin/hostless + the isolated session, from any cwd):
#   hostless cua-x11-session.sh <packet>/run_recert.sh <worktree> <driver-bin> <script> [args...]
# <script> is relative to this packet dir (harness/probe_delivery.py, harness/probe_activation.py,
# probe_sessions_observed.py). Same contract as harness/run_in_session.sh (copied unchanged from BUG-01),
# whose packet path is hard-coded to the BUG-01 dir; this wrapper only points at this packet instead.
# Default Driver safety settings: no permission-mode override, no approval bypass, Chromium sandbox on.
set -uo pipefail
WT="$1"; DRV="$2"; SCRIPT="$3"; shift 3
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: not under bin/hostless" >&2; exit 96; }
for v in CUA_E2E_BROWSER_NO_SANDBOX CUA_DRIVER_PERMISSION_MODE; do
  [ -z "${!v:-}" ] || { echo "refusing: $v is set" >&2; exit 95; }
done
export CUA_DRIVER_BIN="$DRV"
PKT="$WT/docs/experiments/recert-bug01-main-a9baa8d10-2026-10-03"
cd "$WT/libs/cua-driver/examples/jev-use" || exit 98
echo "== recert-bug01 script=$SCRIPT DISPLAY=$DISPLAY lock_note=caller-held"
.venv/bin/python "$PKT/$SCRIPT" "$@"
rc=$?
echo "rc_probe=$rc"
exit $rc
