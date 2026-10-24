#!/usr/bin/env bash
# Run inside the owned container as uid 1000. Never inherit host routing.
set -euo pipefail
export HOME=/home/cua USER=cua LOGNAME=cua
export XDG_RUNTIME_DIR
XDG_RUNTIME_DIR=$(mktemp -d /tmp/hobbylm-runtime.XXXXXX)
export XDG_CONFIG_HOME=/tmp/hobbylm-config XDG_CACHE_HOME=/tmp/hobbylm-cache
export XDG_CURRENT_DESKTOP=sway XDG_SESSION_TYPE=wayland
export GDK_BACKEND=wayland QT_QPA_PLATFORM=wayland
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export LIBSEAT_BACKEND=noop
export CUA_DRIVER_RS_ENABLE_WAYLAND=1
unset DISPLAY WAYLAND_DISPLAY SWAYSOCK HYPRLAND_INSTANCE_SIGNATURE WAYLAND_SOCKET
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
chmod 700 "$XDG_RUNTIME_DIR"
cat > "$XDG_CONFIG_HOME/sway.conf" <<'EOF'
xwayland disable
output HEADLESS-1 mode 1440x1000
seat seat0 xcursor_theme Adwaita 24
EOF
if [[ -z ${DBUS_SESSION_BUS_ADDRESS:-} ]]; then
    exec dbus-run-session -- "$0"
fi
sway --unsupported-gpu --config "$XDG_CONFIG_HOME/sway.conf" > /tmp/hobbylm-sway.log 2>&1 &
sway_pid=$!
trap 'kill "$sway_pid" 2>/dev/null || true' EXIT
for attempt in {1..100}; do
    sockets=("$XDG_RUNTIME_DIR"/sway-ipc.*.sock)
    wayland=("$XDG_RUNTIME_DIR"/wayland-*)
    if [[ -S ${sockets[0]} && -S ${wayland[0]} ]]; then
        export SWAYSOCK=${sockets[0]} WAYLAND_DISPLAY=${wayland[0]##*/}
        break
    fi
    kill -0 "$sway_pid" || exit 1
    sleep 0.1
done
[[ -S ${SWAYSOCK:-/nonexistent} && -S "$XDG_RUNTIME_DIR/${WAYLAND_DISPLAY:-missing}" ]]
swaymsg -s "$SWAYSOCK" -t get_outputs > /tmp/hobbylm-outputs.json
# JSON state is only an ownership guard, never a task-success oracle.
printf '%s\n' '{"owner":"HobbyCuaEval","environment":"owned-linux-sway-v1"}' > /tmp/hobbylm-eval-owned.json
{
    printf 'export XDG_RUNTIME_DIR=%q\n' "$XDG_RUNTIME_DIR"
    printf 'export SWAYSOCK=%q\n' "$SWAYSOCK"
    printf 'export WAYLAND_DISPLAY=%q\n' "$WAYLAND_DISPLAY"
    printf 'export DBUS_SESSION_BUS_ADDRESS=%q\n' "$DBUS_SESSION_BUS_ADDRESS"
    printf 'export HOME=%q GDK_BACKEND=wayland QT_QPA_PLATFORM=wayland XDG_CURRENT_DESKTOP=sway XDG_SESSION_TYPE=wayland\n' "$HOME"
} > /tmp/hobbylm-desktop.env
# The private dummy audio sink never connects to the host's audio server.
pipewire > /tmp/hobbylm-pipewire.log 2>&1 &
pipewire-pulse > /tmp/hobbylm-pulse.log 2>&1 &
wireplumber > /tmp/hobbylm-wireplumber.log 2>&1 &
for attempt in {1..100}; do
    pactl info >/dev/null 2>&1 && break
    sleep 0.1
done
pactl load-module module-null-sink sink_name=hobbylm >/tmp/hobbylm-sink-id
pactl set-default-sink hobbylm
pactl set-sink-volume hobbylm 50%
pactl set-sink-mute hobbylm 0
# Token is an experiment-only local fixture. No host credentials enter the guest.
export CUA_ENV_TOKEN=hobbylm-owned-local-eval CUA_ENV_PORT=3211 CUA_ENV_ALLOW_ANONYMOUS=0
/usr/local/bin/cua-spacesd > /tmp/hobbylm-spacesd.log 2>&1 &
spacesd_pid=$!
trap 'kill "$spacesd_pid" "$sway_pid" 2>/dev/null || true' EXIT
wait "$sway_pid"
