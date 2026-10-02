#!/usr/bin/env bash
# usage (always via the isolated session, from the worktree root):
#   cua-x11-session.sh <packet>/run_in_session.sh <worktree> <driver-bin> <outdir> [run_cross_surface args...]
# Default Driver safety settings: no permission-mode override, no approval
# bypass, Chromium sandbox on, isolated_new profiles only. Refuses to run
# outside the private X11 session. Records Driver/Chrome identity inside the
# session (never on the host desktop).
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"; shift 3
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
for v in CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_DRIVER_PERMISSION_MODE CUA_E2E_BROWSER_NO_SANDBOX; do
  [ -z "${!v:-}" ] || { echo "refusing: $v is set" >&2; exit 96; }
done
PKT="$WT/docs/experiments/r2-08-2026-10-02"
cd "$WT/libs/cua-driver/examples/jev-use" || exit 98
mkdir -p "$(dirname "$OUT")"
echo "== r2-08 DISPLAY=$DISPLAY args=$*"
echo "== driver_version=$("$DRV" --version 2>&1 | head -1)"
echo "== driver_sha256=$(sha256sum "$DRV" | cut -d' ' -f1)"
echo "== chrome_version=$(/opt/google/chrome/chrome --version 2>/dev/null | tail -1)"
echo "== loadavg=$(cat /proc/loadavg)"
.venv/bin/python "$PKT/run_cross_surface.py" --driver "$DRV" --out "$OUT" "$@"
rc=$?
echo "rc_run=$rc"
exit $rc
