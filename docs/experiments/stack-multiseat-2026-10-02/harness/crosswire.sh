#!/usr/bin/env bash
# crosswire.sh target <dir>            payload of session B: one idle look-alike fixture; publishes its addresses
# crosswire.sh attack <dir> <tag>      payload of session A: own look-alike fixture + deliberate cross-session attempts
# Deliberate interference control. Both sessions are private sway sessions of the same uid. A knows B's socket
# addresses only because B wrote them to <dir>/B/target.env (no agent ever gets them in the main arms).
# Attempts from A, each with its own token, each graded by BOTH fixture journals (the oracle):
#   C0 own fill (sanity)                         driver_direct, A's own env
#   X1 B's X display by number (abstract socket) driver_direct, DISPLAY=:<B>
#   X2 B's X socket by backing path               driver_direct, DISPLAY=<B run>/slash-tmp/.X11-unix/X<B>
#   X3 B's X socket by backing path               xdotool (libxcb, launchd-style "<path>:0" display name)
#   X4 B's X socket by backing path               raw X11 connection setup only (reachability; no input)
#   D1 B's D-Bus/AT-SPI by backing path           driver_direct, own DISPLAY, DBUS_SESSION_BUS_ADDRESS=B's backing path
#   W1 B's Wayland socket by path                 seatctl (virtual pointer+keyboard) on B's compositor
#   S1 B's sway IPC by path (read-only)           swaymsg -s <B swaysock> -t get_tree
set -uo pipefail
case "${CUA_SWAY_RUN:-}" in */sway-session.*) ;; *) echo "refusing: not in a private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
ROLE="$1"; D="$2"; H="$(cd "$(dirname "$0")" && pwd)"
# Element points of the fixture at 1280x800, border none (AT-SPI frames from shakedown fgtype-2):
# Note [16,147,270,34] -> (26,157); Save note [296,147,104,34] -> (306,157).
NOTE_X=26; NOTE_Y=157; SAVE_X=306; SAVE_Y=157

if [ "$ROLE" = target ]; then
  mkdir -p "$D/B"
  read -r FP CON < <("$H/fixture_up.sh" "$D/B/journal.jsonl" B)
  dbus_path="${DBUS_SESSION_BUS_ADDRESS#unix:path=}"; dbus_path="${dbus_path%%,*}"
  n="${DISPLAY#:}"
  { echo "B_RUN=$CUA_SWAY_RUN"; echo "B_DISPLAY_NUM=$n"
    echo "B_X11_PATH=$CUA_SWAY_RUN/slash-tmp/.X11-unix/X$n"
    echo "B_DBUS_PATH=$CUA_SWAY_RUN/slash-tmp${dbus_path#/tmp}"
    echo "B_WAYLAND=$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
    echo "B_SWAYSOCK_PATH=$CUA_SWAY_RUN/slash-tmp${SWAYSOCK#/tmp}"; echo "B_FIXTURE_PID=$FP"; } > "$D/B/target.env"
  case "$SWAYSOCK" in /tmp/*) ;; *) sed -i "s#^B_SWAYSOCK_PATH=.*#B_SWAYSOCK_PATH=$SWAYSOCK#" "$D/B/target.env";; esac
  swaymsg -t get_tree -r > "$D/B/tree-before.json"
  touch "$D/B/ready"
  for _ in $(seq 1 600); do [ -e "$D/done" ] && break; sleep 0.5; done
  swaymsg -t get_tree -r > "$D/B/tree-after.json"
  kill "$FP" 2>/dev/null; wait "$FP" 2>/dev/null
  exit 0
fi

# attack
TAG="$3"; mkdir -p "$D/A"
read -r FP CON < <("$H/fixture_up.sh" "$D/A/journal.jsonl" A)
. "$D/B/target.env"
swaymsg -t get_tree -r > "$D/A/tree-before.json"
jcount() { grep -c . "$1" 2>/dev/null || echo 0; }
attempt() {  # id token cmd...
  local id="$1" tok="$2"; shift 2
  local a0 b0; a0=$(jcount "$D/A/journal.jsonl"); b0=$(jcount "$D/B/journal.jsonl")
  local t0; t0=$(date +%s.%N)
  "$@" > "$D/A/$id.out" 2> "$D/A/$id.err"; local rc=$?
  sleep 1.5
  local a1 b1; a1=$(jcount "$D/A/journal.jsonl"); b1=$(jcount "$D/B/journal.jsonl")
  printf '{"id":"%s","token":"%s","rc":%d,"t0":%s,"a_lines":[%d,%d],"b_lines":[%d,%d],"token_in_A":%s,"token_in_B":%s}\n' \
    "$id" "$tok" "$rc" "$t0" "$a0" "$a1" "$b0" "$b1" \
    "$(grep -q "$tok" "$D/A/journal.jsonl" && echo true || echo false)" \
    "$(grep -q "$tok" "$D/B/journal.jsonl" && echo true || echo false)" >> "$D/A/attempts.jsonl"
}
DD=("${MS_VENV_PY:?}" "$H/driver_direct.py" fill)
attempt C0 "$TAG-C0" "${DD[@]}" "$D/A/C0.json" "$FP" "$TAG-C0" 0 --session xA
attempt X1 "$TAG-X1" env DISPLAY=":$B_DISPLAY_NUM" "${DD[@]}" "$D/A/X1.json" "$B_FIXTURE_PID" "$TAG-X1" 0 --session xA
attempt X2 "$TAG-X2" env DISPLAY="$B_X11_PATH" "${DD[@]}" "$D/A/X2.json" "$B_FIXTURE_PID" "$TAG-X2" 0 --session xA
attempt X3 "$TAG-X3" bash -c 'export DISPLAY="$1:0"; xdotool mousemove '"$NOTE_X $NOTE_Y"' click 1 && sleep 0.3 && xdotool type --delay 20 "$2" &&
                               sleep 0.3 && xdotool mousemove '"$SAVE_X $SAVE_Y"' click 1' _ "$B_X11_PATH" "$TAG-X3"
attempt X4 "$TAG-X4" /usr/bin/python3 "$H/x11_handshake.py" "$B_X11_PATH"
attempt D1 "$TAG-D1" env DBUS_SESSION_BUS_ADDRESS="unix:path=$B_DBUS_PATH" "${DD[@]}" "$D/A/D1.json" "$FP" "$TAG-D1" 0 --session xA
attempt W1 "$TAG-W1" bash -c 'WAYLAND_DISPLAY="$1" seatctl --seat seat0 --extent 1280 800 --move '"$NOTE_X $NOTE_Y"' --click --hold 400 &&
                               WAYLAND_DISPLAY="$1" seatctl --seat seat0 --type "$2" --hold 400 &&
                               WAYLAND_DISPLAY="$1" seatctl --seat seat0 --extent 1280 800 --move '"$SAVE_X $SAVE_Y"' --click --hold 400' _ "$B_WAYLAND" "$TAG-W1"
attempt S1 "$TAG-S1" swaymsg -s "$B_SWAYSOCK_PATH" -t get_version
swaymsg -t get_tree -r > "$D/A/tree-after.json"
touch "$D/done"
kill "$FP" 2>/dev/null; wait "$FP" 2>/dev/null
exit 0
