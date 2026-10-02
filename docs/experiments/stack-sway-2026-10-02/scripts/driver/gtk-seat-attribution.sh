#!/usr/bin/env bash
# Inside a 2-seat sway session: does GTK3 (native Wayland) accept clicks from seat0 / seat1 delivered by a
# held virtual pointer (seatctl), independent of the Driver? Oracle: the fixture's own state file.
set -uo pipefail
OUT="$1"; WT="$2"; mkdir -p "$OUT"
case "${XDG_RUNTIME_DIR:-}" in <TMP>/sway-session.*) ;; *) exit 97;; esac
S="$OUT/fixture-state.json"
CUA_GTK3_TASK_STATE="$S" /usr/bin/python3 "$WT/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py" > "$OUT/gtk3.log" 2>&1 &
G=$!
sleep 3
swaymsg -t get_tree -r > "$OUT/tree.json"
# Increment button centre on screen, read off grim screen.png of this exact layout: (70,86) (button spans x 18-122, y 71-102).
# (The Driver-reported screen_point for the same button was (90,107), outside the button.)
for seat in seat0 seat1; do
  seatctl --seat $seat --extent 1920 1080 --move ${CX:-70} ${CY:-86} --click --hold 600 >> "$OUT/seatctl.jsonl" 2>&1
  sleep 0.5; echo "$seat -> $(cat "$S")" | tee -a "$OUT/states.txt"
done
kill $G; wait $G 2>/dev/null
