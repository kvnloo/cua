#!/usr/bin/env bash
# kvnloo/cua#107 lane AB: one block, run INSIDE the private X11 session.
#   host shell: <lanes>/bin/hostless <lanes>/bin/quiet-timed <label> \
#       <lanes>/cua-x11-session.sh <this script> <worktree> <bin-dir> <out-dir> <plan> <label> [runner args]
# The quiet-lane lock is therefore taken before the session (and the Driver MCP session) starts.
set -uo pipefail
WT="$1"; BIN="$2"; OUT="$3"; PLAN="$4"; LABEL="$5"; shift 5
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the private X11 session" >&2; exit 97; }
# Isolation evidence: the hostless wrapper runs us in an unprivileged user namespace, so the uid map
# is not the identity map of the initial namespace. Refuse otherwise (never run outside the wrapper).
if [ "$(tr -s ' ' < /proc/self/uid_map | sed 's/^ //')" = "0 0 4294967295" ]; then
  echo "refusing: not inside the isolation wrapper (initial user namespace)" >&2; exit 98
fi
J="$WT/libs/cua-driver/examples/jev-use"
export JEV_USE_DIR="$J"
mkdir -p "$OUT"
{ echo "uid_map: $(tr -s ' ' < /proc/self/uid_map | sed 's/^ //')"; echo "driver_version: $("$BIN/cua-driver-i107-092b065d5" --version 2>&1)"; } > "$OUT/session-env-$PLAN.txt"
cd "$WT/docs/experiments/i107-ab-2026-10-02"
exec "$J/.venv/bin/python" run_critpath.py --driver "$BIN/cua-driver-i107-092b065d5" \
  --ref-driver "$BIN/cua-driver-r2-main-229b65b28" --out "$OUT" --plan "$PLAN" --lock-label "$LABEL" "$@"
