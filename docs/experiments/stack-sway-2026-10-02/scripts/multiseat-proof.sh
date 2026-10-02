#!/usr/bin/env bash
# usage: CUA_SWAY_SEATS=2 CUA_SWAY_OUTPUTS=1280x720 hostless cua-sway-session.sh multiseat-proof.sh <outdir>
# Two seatprobe windows (L, R) tiled side by side. Per seat, seatctl creates a virtual pointer +
# virtual keyboard bound to that wl_seat. seat0 drives L, seat1 drives R, concurrently. Oracles:
#   - each probe's own per-seat event log (the compositor names the seat of every event);
#   - swaymsg -t get_seats (per-seat focus + attached devices) and get_tree (window ids/rects);
#   - grim screenshot with cursors composited.
set -uo pipefail
OUT="$1"; mkdir -p "$OUT"
case "${XDG_RUNTIME_DIR:-}" in <TMP>/sway-session.*) ;; *) echo "refusing: not in private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
W=1280; H=720
mark() { echo "$1 $(date +%s.%3N)" >> "$OUT/phases.txt"; }
: > "$OUT/phases.txt"
seatprobe L 60 > "$OUT/probe-L.jsonl" 2>"$OUT/probe-L.err" &
PL=$!
sleep 0.7
seatprobe R 60 > "$OUT/probe-R.jsonl" 2>"$OUT/probe-R.err" &
PR=$!
for _ in $(seq 1 50); do
  [ "$(swaymsg -t get_tree -r | grep -c '"app_id": "cua-seatprobe"')" = 2 ] && break; sleep 0.1
done
sleep 0.5
swaymsg -t get_tree -r > "$OUT/tree.json"
read -r LID LCX LCY RID RCX RCY < <(python3 - "$OUT/tree.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))
def walk(n):
    yield n
    for k in ("nodes", "floating_nodes"):
        for c in n.get(k, []):
            yield from walk(c)
v = {n["name"]: n for n in walk(t) if n.get("app_id") == "cua-seatprobe"}
out = []
for name in ("L", "R"):
    r = v[name]["rect"]
    out += [v[name]["id"], r["x"] + r["width"] // 2, r["y"] + r["height"] // 2]
print(*out)
PY
)
echo "L id=$LID center=($LCX,$LCY)  R id=$RID center=($RCX,$RCY)" | tee "$OUT/layout.txt"
swaymsg -t get_seats -r > "$OUT/seats-0-before.json"

mark A; echo "== phase A: concurrent pointer move+click, seat0 -> L, seat1 -> R (devices held 4s)"
seatctl --seat seat0 --extent $W $H --move "$LCX" "$LCY" --click --hold 4000 > "$OUT/seatctl-A-seat0.jsonl" 2>&1 &
A0=$!
seatctl --seat seat1 --extent $W $H --move "$RCX" "$RCY" --click --hold 4000 > "$OUT/seatctl-A-seat1.jsonl" 2>&1 &
A1=$!
sleep 2
swaymsg -t get_seats -r > "$OUT/seats-A-devices-held.json"
grim -c "$OUT/screen-A-two-cursors.png" 2>"$OUT/grim.err"
wait $A0 $A1

mark B; echo "== phase B: concurrent typing, seat0 types 'left', seat1 types 'right'"
seatctl --seat seat0 --type left --hold 1500 > "$OUT/seatctl-B-seat0.jsonl" 2>&1 &
B0=$!
seatctl --seat seat1 --type right --hold 1500 > "$OUT/seatctl-B-seat1.jsonl" 2>&1 &
B1=$!
sleep 1.0; swaymsg -t get_seats -r > "$OUT/seats-B-keyboards-held.json"; wait $B0 $B1
sleep 0.3
swaymsg -t get_seats -r > "$OUT/seats-B-after-typing.json"

mark C; echo "== phase C: only seat0 moves, to (100,100) inside L; seat1 is not touched"
seatctl --seat seat0 --extent $W $H --move 100 100 --hold 800 > "$OUT/seatctl-C-seat0.jsonl" 2>&1 &
C0=$!
sleep 0.5
grim -c "$OUT/screen-C-seat0-moved.png" 2>>"$OUT/grim.err"
wait $C0

mark D; echo "== phase D: swap, concurrently: seat0 -> R at (1100,200), seat1 -> L at (320,600); both click"
seatctl --seat seat0 --extent $W $H --move 1100 200 --click --hold 2500 > "$OUT/seatctl-D-seat0.jsonl" 2>&1 &
D0=$!
seatctl --seat seat1 --extent $W $H --move 320 600 --click --hold 2500 > "$OUT/seatctl-D-seat1.jsonl" 2>&1 &
D1=$!
sleep 1.5
swaymsg -t get_seats -r > "$OUT/seats-D-swapped.json"
grim -c "$OUT/screen-D-swapped.png" 2>>"$OUT/grim.err"
wait $D0 $D1

mark E; echo "== phase E: concurrent typing after swap: seat0 types 'zero' (-> R), seat1 types 'one' (-> L)"
seatctl --seat seat0 --type zero > "$OUT/seatctl-E-seat0.jsonl" 2>&1 &
E0=$!
seatctl --seat seat1 --type one > "$OUT/seatctl-E-seat1.jsonl" 2>&1 &
E1=$!
wait $E0 $E1
sleep 0.3
swaymsg -t get_seats -r > "$OUT/seats-E-after-typing.json"
mark END
kill $PL $PR 2>/dev/null; wait $PL $PR 2>/dev/null
swaymsg -t get_version -r > "$OUT/sway-version.json"
echo "LID=$LID RID=$RID LCX=$LCX LCY=$LCY RCX=$RCX RCY=$RCY" > "$OUT/ids.env"
echo "done"
