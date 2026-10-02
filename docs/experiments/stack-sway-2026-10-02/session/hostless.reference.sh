#!/usr/bin/env bash
# hostless <cmd...>: run a command with no route to the host desktop session.
# Masks the host X11/ICE socket dirs and the user runtime dir (Wayland/Hyprland sockets, session
# D-Bus, AT-SPI bus, portals) with private tmpfs mounts and drops every desktop/session variable,
# so a stray GUI library call (GTK/Qt init, xinput, a browser, cua-driver) fails instead of reaching
# the user's Hyprland desktop. Private sessions (cua-x11-session.sh, cua-sway-session.sh) still work
# inside it: their sockets land on the private mounts or under /mnt.
set -euo pipefail
uid="$(id -u)"
mkdir -p /tmp/.X11-unix /tmp/.ICE-unix 2>/dev/null || true
exec bwrap --dev-bind / / \
  --tmpfs /tmp/.X11-unix --tmpfs /tmp/.ICE-unix --tmpfs "/run/user/$uid" \
  --unsetenv DISPLAY --unsetenv WAYLAND_DISPLAY --unsetenv WAYLAND_SOCKET \
  --unsetenv HYPRLAND_INSTANCE_SIGNATURE --unsetenv HYPRLAND_CMD --unsetenv SWAYSOCK --unsetenv I3SOCK \
  --unsetenv XDG_RUNTIME_DIR --unsetenv DBUS_SESSION_BUS_ADDRESS --unsetenv AT_SPI_BUS_ADDRESS \
  --unsetenv XAUTHORITY --unsetenv XDG_SESSION_TYPE --unsetenv XDG_CURRENT_DESKTOP --unsetenv DESKTOP_SESSION \
  --setenv CUA_HOSTLESS 1 --die-with-parent -- "$@"
