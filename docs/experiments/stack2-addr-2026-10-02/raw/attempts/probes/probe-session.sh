#!/usr/bin/env bash
# probe-session.sh <hermes_wt> <venv> <driver> <out.json>  -- run inside hostless cua-x11-session.sh with CUA_SESSION_ATSPI=1
set -uo pipefail
case "${XDG_RUNTIME_DIR:-}" in */x11-session.*/xdg-runtime) ;; *) echo "refusing: not inside the private X11 session" >&2; exit 97;; esac
WT="$1"; VENV="$2"; DRV="$3"; OUT="$4"
C=<cua_lanes>/stack2-addr/libs/cua-driver
P=<lane_tmp>/probe
export HERMES_HOME="$HOME/.hermes"; mkdir -p "$HERMES_HOME"
export HERMES_CUA_DRIVER_CMD="$DRV" CUA_DRIVER_RS_TELEMETRY_ENABLED=0
CUA_GTK3_TASK_STATE="$TMPDIR/gtk3-state.json" /usr/bin/python3 "$C/tests/fixtures/apps/linux/gtk3/main.py" > "$TMPDIR/gtk.log" 2>&1 &
GP=$!
/usr/bin/python3 <cua_lanes>/stack2-addr/docs/experiments/stack-smoke-2026-10-02/harness/fixture_serve.py "$C/examples/jev-use/fixture_server.py" "$TMPDIR/port" > "$TMPDIR/fx.log" 2>&1 &
FP=$!
for _ in $(seq 50); do [ -s "$TMPDIR/port" ] && break; sleep 0.1; done; PORT=$(cat "$TMPDIR/port")
ACCESSIBILITY_ENABLED=1 /opt/google/chrome/chrome --user-data-dir="$TMPDIR/chrome-profile" --no-first-run --no-default-browser-check \
  --disable-sync --password-store=basic --disable-background-networking --disable-component-update --no-pings \
  --proxy-server=http://127.0.0.1:9 --force-renderer-accessibility --window-size=1100,800 \
  --app=http://127.0.0.1:$PORT/ > "$TMPDIR/chrome.log" 2>&1 &
CP=$!
sleep 4; dbus-send --session --print-reply --dest=org.a11y.Bus /org/a11y/bus org.freedesktop.DBus.Properties.Set string:org.a11y.Status string:IsEnabled variant:boolean:true >/dev/null 2>&1; sleep 4
"$VENV/bin/python" "$P/probe_addr.py" "$WT" "$PORT" > "$OUT" 2> "$OUT.err"
echo "probe rc=$?"
curl -s --noproxy '*' "http://127.0.0.1:$PORT/state"; echo
kill $CP $FP $GP 2>/dev/null; wait 2>/dev/null
