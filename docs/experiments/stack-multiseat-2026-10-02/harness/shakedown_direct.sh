#!/usr/bin/env bash
# shakedown_direct.sh <outdir> <note> <increments>   (inside a private 1-seat sway session, CUA_SESSION_ATSPI=1)
# Model-free pipeline check: journaled fixture + scripted Driver fill. Not a measured run.
set -uo pipefail
OUT="$1"; NOTE="$2"; INC="$3"; mkdir -p "$OUT"
H="$(cd "$(dirname "$0")" && pwd)"
read -r FP CON < <("$H/fixture_up.sh" "$OUT/journal.jsonl" shake)
sleep 1
swaymsg -t get_tree -r > "$OUT/tree-before.json"
"${MS_VENV_PY:?}" "$H/driver_direct.py" fill "$OUT/driver.json" "$FP" "$NOTE" "$INC" ${MS_DIRECT_ARGS:-} > "$OUT/driver.stdout" 2> "$OUT/driver.stderr"
echo "driver rc=$?" >> "$OUT/driver.stdout"
sleep 1
swaymsg -t get_tree -r > "$OUT/tree-after.json"
swaymsg -t get_seats -r > "$OUT/seats-after.json"
grim "$OUT/screen.png" 2>/dev/null
kill "$FP" 2>/dev/null; wait "$FP" 2>/dev/null
cp "$OUT/journal.jsonl.state.json" "$OUT/final-state.json" 2>/dev/null
tail -3 "$OUT/journal.jsonl"
