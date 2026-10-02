#!/usr/bin/env bash
# fixture_up.sh <journal.jsonl> <instance-id> [x11|wayland]
# Inside a private sway session: start one journaled GTK3 task fixture and wait until sway maps it.
# Prints "<pid> <sway-con-id>" on stdout. The fixture runs as an X11 client via the private Xwayland by
# default (the Driver's X11 path; its native Wayland path mis-scales element frames, see the sway packet).
# The window's server-side border is removed (MS_KEEP_BORDER=1 keeps it) - see below.
set -uo pipefail
case "${CUA_SWAY_RUN:-}" in */sway-session.*) ;; *) echo "refusing: not in a private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
J="$1"; ID="$2"; BACKEND="${3:-x11}"
H="$(cd "$(dirname "$0")" && pwd)"
GTK3_MAIN="${MS_GTK3_MAIN:?MS_GTK3_MAIN (upstream gtk3 main.py) not set}"
if [ "$BACKEND" = x11 ]; then
  env -u WAYLAND_DISPLAY GDK_BACKEND=x11 /usr/bin/python3 "$H/journaled_fixture.py" "$GTK3_MAIN" "$J" "$ID" > "$J.log" 2>&1 &
else
  GDK_BACKEND=wayland /usr/bin/python3 "$H/journaled_fixture.py" "$GTK3_MAIN" "$J" "$ID" > "$J.log" 2>&1 &
fi
P=$!
for _ in $(seq 1 100); do
  con="$(swaymsg -t get_tree -r | P=$P /usr/bin/python3 -c '
import json, os, sys
t = json.load(sys.stdin); pid = int(os.environ["P"])
def walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from walk(c)
print(next((n["id"] for n in walk(t) if n.get("pid") == pid), ""))')"
  if [ -n "$con" ] && grep -q '"kind": "mapped"' "$J" 2>/dev/null; then
    # No server-side decoration: with sway's title bar the Driver's AT-SPI element bounds and its window-local
    # click frame disagree by the decoration offset (+2, +27 px; shakedown hermes-7b-3..5), so clicks at element
    # centres miss. Runtime per-window command only (never "swaymsg seat ...").
    [ "${MS_KEEP_BORDER:-0}" = 1 ] || swaymsg "[con_id=$con] border none" > /dev/null
    # Pointer warm-up (motion only, blank area, no button/key): without it the first XTEST click the Driver sends
    # into a fresh Xwayland is dropped (shakedown fgtype-3: 3 clicks -> counter 2; fgtype-4 with warm-up: 3 -> 3).
    if [ "$BACKEND" = x11 ] && [ "${MS_NO_WARMUP:-0}" != 1 ]; then
      sleep 0.3; xdotool mousemove 640 700; sleep 0.3; xdotool mousemove 5 5; sleep 0.2
    fi
    echo "$P $con"; exit 0
  fi
  sleep 0.1
done
echo "fixture did not map (pid $P)" >&2; echo "$P"; exit 3
