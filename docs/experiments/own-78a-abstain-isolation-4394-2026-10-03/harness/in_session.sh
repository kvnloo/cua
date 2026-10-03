#!/usr/bin/env bash
# Runs inside cua-x11-session.sh: refuses outside a private X11 session, waits a 0-3 s jitter, probes the
# private display with xdpyinfo, then execs the harness.
set -uo pipefail
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
jitter_ms=$(( RANDOM % 3001 ))
sleep "$(printf '%d.%03d' $((jitter_ms/1000)) $((jitter_ms%1000)))"
if xdpyinfo >/dev/null 2>&1; then probe=ok; else probe=fail; fi
echo "{\"event\":\"session_probe\",\"jitter_ms\":$jitter_ms,\"xdpyinfo\":\"$probe\",\"loadavg\":\"$(cut -d' ' -f1-3 /proc/loadavg)\"}"
[ "$probe" = ok ] || exit 96
exec "$@"
