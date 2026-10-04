#!/usr/bin/env bash
# usage (inside hostless + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   run_block.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <block> <label> <raw-out-dir> <work-dir>
# Derived from the N-02 run_block.sh; runs n03_harness.py. Refuses outside the isolated session,
# when the Driver's sha256 differs from the expected one, or when an override variable is set.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; BLOCK="$5"; LABEL="$6"; OUT="$7"; WORK="$8"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX TYPESAFE_API_KEY; do
  [ -z "${!v:-}" ] || { echo "refusing: $v set" >&2; exit 96; }
done
actual="$(sha256sum "$DRV" | cut -d' ' -f1)"
[ "$actual" = "$DSHA" ] || { echo "refusing: driver sha256 $actual != $DSHA" >&2; exit 98; }
mkdir -p "$OUT" "$WORK"
HERE="$(cd "$(dirname "$0")" && pwd)"
echo "[n03] display=$DISPLAY loadavg=$(cut -d' ' -f1-3 /proc/loadavg) atspi=${CUA_SESSION_ATSPI:-0} driver=$(basename "$DRV") version=$("$DRV" --version 2>&1 | head -1)"
exec "$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/n03_harness.py" \
  --wt "$WT" --driver "$DRV" --driver-sha256 "$DSHA" --plan "$PLAN" \
  --plan-sha256 "$(sha256sum "$PLAN" | cut -d' ' -f1)" --block "$BLOCK" --label "$LABEL" \
  --out "$OUT" --work "$WORK"
