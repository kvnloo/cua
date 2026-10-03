#!/usr/bin/env bash
# usage (inside hostless + cua-x11-session.sh with CUA_SESSION_ATSPI=1):
#   run_block.sh <worktree> <driver-U> <sha256-U> <driver-G> <sha256-G> <plan.json> <block> <label> <raw-out-dir> <work-dir>
# Derived from the N-02 run_block.sh; runs own20g_harness.py, or r3_harness.py for R3 blocks
# (plan field "harness").
set -uo pipefail
WT="$1"; DRVU="$2"; SHAU="$3"; DRVG="$4"; SHAG="$5"; PLAN="$6"; BLOCK="$7"; LABEL="$8"; OUT="$9"; WORK="${10}"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
for pair in "$DRVU=$SHAU" "$DRVG=$SHAG"; do
  actual="$(sha256sum "${pair%%=*}" | cut -d' ' -f1)"
  [ "$actual" = "${pair##*=}" ] || { echo "refusing: driver sha256 $actual != ${pair##*=}" >&2; exit 98; }
done
mkdir -p "$OUT" "$WORK"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$WT/libs/cua-driver/examples/jev-use/.venv/bin/python"
HARNESS="$("$PY" -c 'import json,sys; b=[b for b in json.load(open(sys.argv[1]))["blocks"] if b["block"]==sys.argv[2]][0]; print(b.get("harness","own20g_harness.py"))' "$PLAN" "$BLOCK")"
echo "[session] versions: U=$("$DRVU" --version 2>&1 | head -1) G=$("$DRVG" --version 2>&1 | head -1)" >&2
exec "$PY" "$HERE/$HARNESS" \
  --wt "$WT" --driver-u "$DRVU" --driver-u-sha256 "$SHAU" --driver-g "$DRVG" --driver-g-sha256 "$SHAG" \
  --plan "$PLAN" --plan-sha256 "$(sha256sum "$PLAN" | cut -d' ' -f1)" --block "$BLOCK" --label "$LABEL" \
  --out "$OUT" --work "$WORK"
