#!/usr/bin/env bash
# kvnloo/cua#107 lane AB: one block, run INSIDE the private X11 session.
#   host shell: <lanes>/bin/hostless <lanes>/bin/quiet-timed <label> \
#       <lanes>/cua-x11-session.sh <this script> <worktree> <bin-dir> <out-dir> <plan> <label> [runner args]
# The quiet-lane lock is therefore taken before the session (and the Driver MCP session) starts.
set -uo pipefail
WT="$1"; BIN="$2"; OUT="$3"; PLAN="$4"; LABEL="$5"; shift 5
read -r -a PLANS <<< "$PLAN"   # one or more plans, run in order inside this one session
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the private X11 session" >&2; exit 97; }
# Isolation evidence: an ancestor process must carry CUA_HOSTLESS=1 in its environment (set by the
# lanes' hostless wrapper, v1 bwrap or v2 Landlock) - cua-x11-session.sh clears our own environment,
# so we look up the process tree. Refuse otherwise (never run outside the wrapper).
hostless_ancestor=""
p=$$
while [ "$p" -gt 1 ]; do
  if tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qx 'CUA_HOSTLESS=1'; then hostless_ancestor="$p"; break; fi
  p="$(awk '{print $4}' "/proc/$p/stat" 2>/dev/null || echo 1)"
done
[ -n "$hostless_ancestor" ] || { echo "refusing: no hostless ancestor (CUA_HOSTLESS=1) found" >&2; exit 98; }
J="$WT/libs/cua-driver/examples/jev-use"
export JEV_USE_DIR="$J"
mkdir -p "$OUT"
{ echo "hostless_ancestor_found: yes"
  echo "uid_map: $(tr -s ' ' < /proc/self/uid_map | sed 's/^ //')"
  echo "display_is_private: $([ "${DISPLAY#:}" != "0" ] && echo yes || echo no)"
  echo "wayland_display_set: ${WAYLAND_DISPLAY:+yes}"
  echo "driver_version: $("$BIN/cua-driver-i107-092b065d5" --version 2>&1)"; } > "$OUT/session-env-${PLANS[0]}.txt"
cd "$WT/docs/experiments/i107-ab-2026-10-02"
exec "$J/.venv/bin/python" run_critpath.py --driver "$BIN/cua-driver-i107-092b065d5" \
  --ref-driver "$BIN/cua-driver-r2-main-229b65b28" --out "$OUT" --plan "${PLANS[@]}" --lock-label "$LABEL" "$@"
