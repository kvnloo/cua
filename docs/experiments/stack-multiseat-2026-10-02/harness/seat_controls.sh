#!/usr/bin/env bash
# seat_controls.sh lookalike <outdir> <tag>   (CUA_SWAY_SEATS=2 CUA_SWAY_OUTPUTS=1280x720)
#   Single-compositor multi-seat look-alike control, NON-Driver: two seatprobe windows with the SAME title, tiled
#   side by side; seat0 drives the left one and seat1 the right one CONCURRENTLY (click + type a seat-specific token),
#   then they swap. Oracle: each window's own per-seat event log (the compositor names the seat of every event).
# seat_controls.sh driver <outdir> <tag>      (CUA_SWAY_SEATS=2 CUA_SWAY_OUTPUTS=1280x720)
#   Multi-seat Driver replicate: two concurrent cua-driver processes ("agent A" -> left window, "agent B" -> right
#   window), native Wayland arm, foreground pixel clicks. Oracle: seatprobe logs. Expectation from the sway setup:
#   the Driver has no seat selection, so both agents' events arrive on one seat (BLOCKED for per-agent seats).
set -uo pipefail
case "${CUA_SWAY_RUN:-}" in */sway-session.*) ;; *) echo "refusing: not in a private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
MODE="$1"; OUT="$2"; TAG="$3"; mkdir -p "$OUT"; H="$(cd "$(dirname "$0")" && pwd)"
W=1280; HT=720; TITLE="CuaTestHarness GTK3 Tasks"
mark() { echo "$1 $(date +%s.%3N)" >> "$OUT/phases.txt"; }
: > "$OUT/phases.txt"
seatprobe "$TITLE" 90 > "$OUT/probe-1.jsonl" 2> "$OUT/probe-1.err" &
P1=$!
sleep 0.7
seatprobe "$TITLE" 90 > "$OUT/probe-2.jsonl" 2> "$OUT/probe-2.err" &
P2=$!
for _ in $(seq 1 50); do [ "$(swaymsg -t get_tree -r | grep -c '"app_id": "cua-seatprobe"')" = 2 ] && break; sleep 0.1; done
sleep 0.5
swaymsg -t get_tree -r > "$OUT/tree.json"
# Left/right by on-screen x; the two windows are indistinguishable by title.
read -r LPID LID LCX LCY LX LY RPID RID RCX RCY RX RY < <(/usr/bin/python3 - "$OUT/tree.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))
def walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from walk(c)
v = sorted((n for n in walk(t) if n.get("app_id") == "cua-seatprobe"), key=lambda n: n["rect"]["x"])
out = []
for n in v:
    r = n["rect"]
    out += [n["pid"], n["id"], r["x"] + r["width"] // 2, r["y"] + r["height"] // 2, r["x"], r["y"]]
print(*out)
PY
)
if [ "$LPID" != "$P1" ]; then tmp=$P1; P1=$P2; P2=$tmp; fi   # P1 := left window's process
echo "L pid=$LPID id=$LID c=($LCX,$LCY) R pid=$RPID id=$RID c=($RCX,$RCY) P1=$P1 P2=$P2" | tee "$OUT/layout.txt"
swaymsg -t get_seats -r > "$OUT/seats-before.json"
if [ "$MODE" = lookalike ]; then
  mark A
  seatctl --seat seat0 --extent $W $HT --move "$LCX" "$LCY" --click --hold 600 > "$OUT/A-seat0-click.jsonl" 2>&1 &
  a0=$!; seatctl --seat seat1 --extent $W $HT --move "$RCX" "$RCY" --click --hold 600 > "$OUT/A-seat1-click.jsonl" 2>&1 &
  a1=$!; wait $a0 $a1
  seatctl --seat seat0 --type "${TAG}s0L" --hold 600 > "$OUT/A-seat0-type.jsonl" 2>&1 &
  a0=$!; seatctl --seat seat1 --type "${TAG}s1R" --hold 600 > "$OUT/A-seat1-type.jsonl" 2>&1 &
  a1=$!; wait $a0 $a1
  swaymsg -t get_seats -r > "$OUT/seats-A.json"
  mark B
  seatctl --seat seat0 --extent $W $HT --move "$RCX" "$((RCY + 60))" --click --hold 600 > "$OUT/B-seat0-click.jsonl" 2>&1 &
  b0=$!; seatctl --seat seat1 --extent $W $HT --move "$LCX" "$((LCY + 60))" --click --hold 600 > "$OUT/B-seat1-click.jsonl" 2>&1 &
  b1=$!; wait $b0 $b1
  seatctl --seat seat0 --type "${TAG}s0R" --hold 600 > "$OUT/B-seat0-type.jsonl" 2>&1 &
  b0=$!; seatctl --seat seat1 --type "${TAG}s1L" --hold 600 > "$OUT/B-seat1-type.jsonl" 2>&1 &
  b1=$!; wait $b0 $b1
  swaymsg -t get_seats -r > "$OUT/seats-B.json"
  mark END
else
  # window-local click points: centre of each window (content origin = rect origin under sway's tiling)
  mark DA
  MS_DRIVER_WAYLAND=1 "${MS_VENV_PY:?}" "$H/driver_direct.py" click_xy "$OUT/driver-A.json" "$P1" agentA \
     "$((LCX - LX)),$((LCY - LY))" "$((LCX - LX + 40)),$((LCY - LY + 40))" > "$OUT/driver-A.out" 2>&1 &
  d0=$!
  MS_DRIVER_WAYLAND=1 "${MS_VENV_PY:?}" "$H/driver_direct.py" click_xy "$OUT/driver-B.json" "$P2" agentB \
     "$((RCX - RX)),$((RCY - RY))" "$((RCX - RX + 40)),$((RCY - RY + 40))" > "$OUT/driver-B.out" 2>&1 &
  d1=$!
  wait $d0 $d1
  swaymsg -t get_seats -r > "$OUT/seats-D.json"
  mark END
fi
sleep 0.5
kill $P1 $P2 2>/dev/null; wait $P1 $P2 2>/dev/null
echo "LPID=$LPID RPID=$RPID P1=$P1 P2=$P2" > "$OUT/ids.env"
