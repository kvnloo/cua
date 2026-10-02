#!/usr/bin/env bash
# sandbox-driver.sh <program> [args...]
#
# Runs ONE trial's Driver (champion or candidate, identically) inside a bubblewrap sandbox.
# Must be called from inside the private X11 session (cua-x11-session.sh), never from a host shell.
#
#   - read-only root (remounted ro) built from /usr and /etc only (no /home, no /mnt, no /opt);
#   - tmpfs trial HOME (/home/trial) and tmpfs XDG_RUNTIME_DIR (/run/user/trial);
#   - only these sockets are bound, each at its own path: the session's X socket, the session
#     D-Bus socket, the private AT-SPI bus socket; plus the Xauthority file of the private display;
#   - the harness, the results files and the fixture-state dir are never mounted;
#   - --unshare-net (no network, no abstract sockets), --unshare-ipc/--unshare-uts, --new-session,
#     --die-with-parent;
#   - pid namespace: the SESSION's (AR_SANDBOX_PIDNS=session, default; the session must run under
#     session-pidns.sh). A per-trial --unshare-pid (AR_SANDBOX_PIDNS=private) is NOT usable: the
#     Driver resolves the target app through /proc/<pid> (list_windows keeps only windows whose pid
#     is live in its /proc; process start times, toolkit detection), and the pids it gets from
#     _NET_WM_PID and from AT-SPI peer credentials are session-namespace pids. In the shared session
#     namespace the Driver sees only session processes, and other processes' /proc/<pid>/root and
#     environ are denied to it (child user namespace); the probe records both facts.
#   - environment cleared, then only the display/bus variables, a trial HOME/XDG set and CUA_DRIVER_*
#     variables are passed. CUA_DRIVER_PHASE_TRACE_FILE, when set, is remapped to a per-trial trace dir
#     (the only writable bind), so the measurement-only marks still work.
#
# The program is bound read-only at /run/ar/bin/<name> unless it already lives under /usr.
set -euo pipefail
prog="$1"; shift
[ -n "${DISPLAY:-}" ] && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ] || { echo "sandbox-driver: no private session" >&2; exit 97; }
[ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "sandbox-driver: host session variables present" >&2; exit 97; }

disp="${DISPLAY#:}"; disp="${disp%%.*}"
xsock="/tmp/.X11-unix/X$disp"
dbus_path="${DBUS_SESSION_BUS_ADDRESS#unix:path=}"; dbus_path="${dbus_path%%,*}"
a11y="${AR_A11Y_ADDRESS:-}"
if [ -z "$a11y" ]; then
  a11y="$(gdbus call --session --dest org.a11y.Bus --object-path /org/a11y/bus \
    --method org.a11y.Bus.GetAddress 2>/dev/null | sed -n "s/.*'\(unix:[^']*\)'.*/\1/p")"
fi
a11y_path="${a11y#unix:path=}"; a11y_path="${a11y_path%%,*}"

case "${AR_SANDBOX_PIDNS:-session}" in
  session)
    # Share the session's own pid namespace (session-pidns.sh is its pid 1), never the host's.
    tr '\0' ' ' < /proc/1/cmdline | grep -q 'AR_SESSION_PIDNS' \
      || { echo "sandbox-driver: not inside session-pidns.sh; refusing to share a pid namespace" >&2; exit 97; }
    pidns=() ;;
  private) pidns=(--unshare-pid) ;;  # probe only: hides the target app from the Driver (see header)
  *) echo "sandbox-driver: AR_SANDBOX_PIDNS must be session or private" >&2; exit 97 ;;
esac
args=("${pidns[@]}" --unshare-net --unshare-ipc --unshare-uts --die-with-parent --new-session
  --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/bin /sbin
  --symlink usr/lib /lib --symlink usr/lib /lib64 --ro-bind /etc /etc
  --proc /proc --dev /dev --tmpfs /tmp
  --perms 0700 --tmpfs /home/trial --perms 0700 --tmpfs /run/user/trial
  --ro-bind "$xsock" "$xsock" --ro-bind "$dbus_path" "$dbus_path")
[ -n "$a11y_path" ] && [ -S "$a11y_path" ] && args+=(--ro-bind "$a11y_path" "$a11y_path")
[ -n "${XAUTHORITY:-}" ] && [ -f "$XAUTHORITY" ] && args+=(--ro-bind "$XAUTHORITY" "$XAUTHORITY")

envs=(--clearenv --setenv DISPLAY "$DISPLAY" --setenv DBUS_SESSION_BUS_ADDRESS "$DBUS_SESSION_BUS_ADDRESS"
  --setenv HOME /home/trial --setenv XDG_RUNTIME_DIR /run/user/trial
  --setenv XDG_CONFIG_HOME /home/trial/.config --setenv XDG_CACHE_HOME /home/trial/.cache
  --setenv XDG_STATE_HOME /home/trial/.local/state --setenv XDG_DATA_HOME /home/trial/.local/share
  --setenv XDG_SESSION_TYPE x11 --setenv PATH /usr/bin --setenv LANG C.UTF-8 --setenv TMPDIR /tmp)
[ -n "${XAUTHORITY:-}" ] && envs+=(--setenv XAUTHORITY "$XAUTHORITY")
while IFS='=' read -r name value; do
  case "$name" in
    CUA_DRIVER_PHASE_TRACE_FILE)
      if [ -n "$value" ]; then
        tdir="$(dirname "$value")"; mkdir -p "$tdir"
        args+=(--bind "$tdir" /run/ar/trace)
        envs+=(--setenv "$name" "/run/ar/trace/$(basename "$value")")
      fi ;;
    CUA_DRIVER_*) envs+=(--setenv "$name" "$value") ;;
  esac
done < <(env)

case "$prog" in
  /usr/*) inner="$prog" ;;
  *) inner="/run/ar/bin/$(basename "$prog")"; args+=(--ro-bind "$prog" "$inner") ;;
esac
args+=(--remount-ro /)
exec bwrap "${args[@]}" "${envs[@]}" -- "$inner" "$@"
