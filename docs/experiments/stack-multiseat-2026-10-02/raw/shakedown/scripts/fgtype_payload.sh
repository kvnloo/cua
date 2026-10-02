#!/usr/bin/env bash
# shakedown-only payload (inside a private sway session)
set -uo pipefail
OUT="$1"; mkdir -p "$OUT"
read -r FP CON < <("$MS_H/fixture_up.sh" "$OUT/journal.jsonl" fg)
sleep 1
[ "${WARM:-0}" = 1 ] && xdotool mousemove 640 700 && sleep 0.3 && xdotool mousemove 5 5
"$MS_VENV_PY" <TMP>/multiseat/shake/fgtype_probe.py "$OUT/probe.json" "$FP" > "$OUT/probe.out" 2>&1
sleep 1
swaymsg -t get_seats -r > "$OUT/seats.json"
kill "$FP"; wait "$FP" 2>/dev/null
cut -c1-160 "$OUT/journal.jsonl"
