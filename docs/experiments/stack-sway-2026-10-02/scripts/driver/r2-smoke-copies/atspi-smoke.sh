#!/usr/bin/env bash
# usage (always via the isolated session with a private AT-SPI bus):
#   CUA_SESSION_ATSPI=1 cua-x11-session.sh <lanes>/artifacts/r2/smoke/atspi-smoke.sh <worktree> <driver-bin> <outdir>
# Launches the canonical GTK3 fixture (system python3 + PyGObject) and records one get_window_state
# through the existing jev-use helper python/capture_window_state.py (MCP stdio, tree + screenshot together).
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
mkdir -p "$OUT"
export CUA_DRIVER_BIN="$DRV"
J="$WT/libs/cua-driver/examples/jev-use"
echo "== env DISPLAY=$DISPLAY AT_SPI_BUS_ADDRESS=${AT_SPI_BUS_ADDRESS:-unset} DBUS=${DBUS_SESSION_BUS_ADDRESS:-unset}"
/usr/bin/python3 "$WT/libs/cua-driver/tests/fixtures/apps/linux/gtk3/main.py" > "$OUT/gtk3-fixture.log" 2>&1 &
GPID=$!
sleep 3
cd "$J"
.venv/bin/python python/capture_window_state.py --pid "$GPID" --title "CuaTestHarness GTK3" \
  --source "r2-setup-smoke gtk3 default scenario" --output "$OUT/gtk3-window-state.json"
rc=$?; echo "rc_capture=$rc"
kill "$GPID" 2>/dev/null; wait "$GPID" 2>/dev/null
.venv/bin/python - "$OUT/gtk3-window-state.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
els = s.get("elements") or []
names = sorted({e.get("name") or e.get("label") or "" for e in els} - {""})
want = ["btn-increment", "btn-reset", "txt-input", "chk-agree", "sld-value", "btn-exit"]
print("element_count", len(els))
print("named_count", len(names))
print("expected_present", {w: (w in names) for w in want})
print("sample_names", names[:40])
print("keys", sorted(s.keys()))
PY
exit $rc
