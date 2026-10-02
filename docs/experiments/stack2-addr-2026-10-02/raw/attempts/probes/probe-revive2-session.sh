#!/usr/bin/env bash
# probe-revive2-session.sh <hermes_wt> <venv> <driver> <out.json>  -- run inside hostless cua-x11-session.sh with CUA_SESSION_ATSPI=1
set -uo pipefail
case "${XDG_RUNTIME_DIR:-}" in */x11-session.*/xdg-runtime) ;; *) echo "refusing: not inside the private X11 session" >&2; exit 97;; esac
WT="$1"; VENV="$2"; DRV="$3"; OUT="$4"
C=<cua_lanes>/stack2-addr/libs/cua-driver
P=<lane_tmp>/probe
export HERMES_HOME="$HOME/.hermes"; mkdir -p "$HERMES_HOME"
export HERMES_CUA_DRIVER_CMD="$DRV" CUA_DRIVER_RS_TELEMETRY_ENABLED=0 PYTHONDONTWRITEBYTECODE=1
CUA_GTK3_TASK_STATE="$TMPDIR/gtk3-state.json" /usr/bin/python3 "$C/tests/fixtures/apps/linux/gtk3/main.py" > "$TMPDIR/gtk.log" 2>&1 &
GP=$!
for _ in $(seq 50); do [ -s "$TMPDIR/gtk3-state.json" ] && break; sleep 0.2; done
sleep 1
"$VENV/bin/python" "$P/probe_revive2.py" "$WT" > "$OUT" 2> "$OUT.err"
echo "probe rc=$?"
cat "$TMPDIR/gtk3-state.json"; echo
kill $GP 2>/dev/null; wait 2>/dev/null
