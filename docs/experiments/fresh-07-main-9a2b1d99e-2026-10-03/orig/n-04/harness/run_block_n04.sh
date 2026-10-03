#!/usr/bin/env bash
# usage (inside hostless + hostless-strict + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   run_block_n04.sh <worktree> <driver-bin> <driver-sha256> <plan.json> <runs-dir> <work-dir> <prefix> <chunk> [--no-load-gate] <block>...
# Derived from the N-03 run_block.sh. Refuses outside the isolated session, when the Driver's sha256
# differs from the expected one, or when an override variable is set. Before trusting the session it
# waits a random 0-3 s and probes the private X server with xdpyinfo; then it reads the Driver version
# inside the session and runs n04_harness.py for the given rounds.
set -uo pipefail
WT="$1"; DRV="$2"; DSHA="$3"; PLAN="$4"; RUNS="$5"; WORK="$6"; PREFIX="$7"; CHUNK="$8"; shift 8
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX TYPESAFE_API_KEY; do
  [ -z "${!v:-}" ] || { echo "refusing: $v set" >&2; exit 96; }
done
actual="$(sha256sum "$DRV" | cut -d' ' -f1)"
[ "$actual" = "$DSHA" ] || { echo "refusing: driver sha256 $actual != $DSHA" >&2; exit 98; }
mkdir -p "$RUNS" "$WORK"
jitter_ms=$(( RANDOM % 3001 ))
sleep "$(printf '%d.%03d' $((jitter_ms / 1000)) $((jitter_ms % 1000)))"
if ! xdpyinfo -display "$DISPLAY" > "$WORK/xdpyinfo-$CHUNK.txt" 2>&1; then
  echo "[n04] session NOT trusted: xdpyinfo probe failed on $DISPLAY (jitter ${jitter_ms} ms)" >&2; exit 93
fi
screen="$(grep -m1 'dimensions:' "$WORK/xdpyinfo-$CHUNK.txt" | awk '{print $2}')"
echo "[n04] chunk=$CHUNK display=$DISPLAY xdpyinfo=ok screen=$screen jitter_ms=$jitter_ms loadavg=$(cut -d' ' -f1-3 /proc/loadavg) atspi=${CUA_SESSION_ATSPI:-0} telemetry=${CUA_DRIVER_RS_TELEMETRY_ENABLED:-unset} dnt=${DO_NOT_TRACK:-unset} driver=$(basename "$DRV") sha256=$actual version=$("$DRV" --version 2>&1 | head -1)"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$WT/libs/cua-driver/examples/jev-use/.venv/bin/python" "$HERE/n04_harness.py" \
  --wt "$WT" --driver "$DRV" --driver-sha256 "$DSHA" --plan "$PLAN" --runs "$RUNS" --work "$WORK" \
  --prefix "$PREFIX" --chunk "$CHUNK" "$@"
rc=$?
echo "[n04] chunk=$CHUNK harness rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg) version_end=$("$DRV" --version 2>&1 | head -1)"
exit $rc
