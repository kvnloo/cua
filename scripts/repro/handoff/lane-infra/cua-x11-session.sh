#!/usr/bin/env bash
# Focus-safe isolated X11 session for Driver/MCP/Chromium E2E.
#   usage: cua-x11-session.sh <cmd> [args...]
# Runs <cmd> inside a private rootless Xvfb + private dbus session + openbox + picom,
# with a scrubbed environment: NO WAYLAND_DISPLAY / HYPRLAND_* / host XDG_RUNTIME_DIR,
# so neither the Driver nor Chromium can reach Kevin's Hyprland desktop.
set -euo pipefail
ART=/home/kvn/.local/opt/cua-e2e-x11/root      # user-local Xvfb + openbox (checksummed Arch packages)
NODE22=/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin
RUN="$(mktemp -d /mnt/zer0models/cua-lane-tmp/x11-session.XXXXXX)"
chmod 700 "$RUN"; mkdir -p "$RUN/xdg-runtime" "$RUN/home" "$RUN/tmp"; chmod 700 "$RUN/xdg-runtime"
# Optional secret forwarding by NAME (never on a command line): CUA_SESSION_FORWARD_SECRETS="TYPESAFE_API_KEY"
if [ -n "${CUA_SESSION_FORWARD_SECRETS:-}" ]; then
  ( umask 077; : > "$RUN/secrets.sh"
    for n in $CUA_SESSION_FORWARD_SECRETS; do
      if [ -n "${!n:-}" ]; then printf 'export %s=%q\n' "$n" "${!n}" >> "$RUN/secrets.sh"; fi
    done )
fi
CMD_FILE="$RUN/cmd.sh"
{ echo '#!/usr/bin/env bash'; echo 'set -uo pipefail'
  printf 'cd %q\n' "$PWD"
  printf 'exec'; for a in "$@"; do printf ' %q' "$a"; done; echo
} > "$CMD_FILE"; chmod 700 "$CMD_FILE"
cat > "$RUN/inner.sh" <<INNER
#!/usr/bin/env bash
set -uo pipefail
export LD_LIBRARY_PATH="$ART/usr/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}"
export XDG_DATA_DIRS="$ART/usr/share:/usr/local/share:/usr/share"
export XDG_CONFIG_DIRS="$ART/etc/xdg:/etc/xdg"
if [ -f "$RUN/secrets.sh" ]; then . "$RUN/secrets.sh"; rm -f "$RUN/secrets.sh"; fi
if [ "\${CUA_SESSION_ATSPI:-0}" = "1" ]; then
  /usr/lib/at-spi-bus-launcher --launch-immediately >"$RUN/atspi-bus.log" 2>&1 &
  sleep 1
  /usr/lib/at-spi2-registryd --use-gnome-session >"$RUN/atspi-registry.log" 2>&1 &
fi
openbox >"$RUN/openbox.log" 2>&1 &
OB=\$!
picom --backend xrender --config /dev/null >"$RUN/picom.log" 2>&1 &
PC=\$!
sleep 2
echo "[session] DISPLAY=\$DISPLAY openbox=\$OB picom=\$PC dbus=\${DBUS_SESSION_BUS_ADDRESS:-none}" >&2
bash "$CMD_FILE"; rc=\$?
kill \$PC \$OB 2>/dev/null; wait \$PC \$OB 2>/dev/null
exit \$rc
INNER
chmod 700 "$RUN/inner.sh"
# Clean environment: nothing from the Wayland/Hyprland host session leaks in.
set +e
env -i \
  HOME="$RUN/home" USER="$USER" LOGNAME="$USER" SHELL=/bin/bash LANG=C.UTF-8 TERM=xterm \
  PATH="$ART/usr/bin:$NODE22:/home/kvn/.local/bin:/home/kvn/.cargo/bin:/usr/local/bin:/usr/bin:/bin" \
  TMPDIR="$RUN/tmp" \
  XDG_RUNTIME_DIR="$RUN/xdg-runtime" XDG_STATE_HOME="$RUN/home/.local/state" \
  XDG_CONFIG_HOME="$RUN/home/.config" XDG_CACHE_HOME="$RUN/home/.cache" XDG_DATA_HOME="$RUN/home/.local/share" \
  XDG_SESSION_TYPE=x11 \
  UV_CACHE_DIR=/home/kvn/.cache/uv \
  ${CUA_SESSION_EXTRA_ENV:-} \
  "$ART/usr/bin/xvfb-run" -a --server-args="-screen 0 1920x1080x24 -nolisten tcp" \
  dbus-run-session -- bash "$RUN/inner.sh"
rc=$?
echo "[session] exit rc=$rc run_dir=$RUN" >&2
exit $rc
