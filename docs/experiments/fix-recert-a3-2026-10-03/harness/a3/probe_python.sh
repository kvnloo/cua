#!/usr/bin/env bash
# RECERT-FIX a3: session probe, then the system python (GTK fixture + native harness).
# Used as OWN36_PYTHON. The first use inside a private session probes the display with xdpyinfo and
# refuses to run if the probe fails or the session is not the private X11 one; later uses (fixture
# launches in the same session) skip the probe.
set -uo pipefail
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "[a3-probe] refusing: not in private X11 session" >&2; exit 97; }
marker="${TMPDIR:?}/.a3-probe-done"
if [ ! -e "$marker" ]; then
  if xdpyinfo > "${TMPDIR}/a3-xdpyinfo.txt" 2>&1; then
    echo "[a3-probe] xdpyinfo ok DISPLAY=$DISPLAY $(grep -m1 'dimensions:' "${TMPDIR}/a3-xdpyinfo.txt" | tr -s ' ')" >&2
    : > "$marker"
  else
    echo "[a3-probe] xdpyinfo FAILED DISPLAY=$DISPLAY" >&2
    exit 95
  fi
fi
exec /usr/bin/python3 "$@"
