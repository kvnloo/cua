#!/usr/bin/env bash
# Runs inside cua-x11-session.sh (private rootless Xvfb + private dbus, scrubbed env).
#   usage: session_entry.sh <worktree> <driver-bin> <out-dir> <tmp-dir> [run_trials args...]
set -uo pipefail
if [ -n "${WAYLAND_DISPLAY:-}" ] || env | grep -q '^HYPRLAND_'; then
  echo "refusing: host Wayland/Hyprland variables present" >&2; exit 97
fi
WT="$1"; BIN="$2"; OUT="$3"; TMP="$4"; shift 4
JEV="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT" "$TMP"
{
  echo "display_set=$([ -n "${DISPLAY:-}" ] && echo yes || echo no)"
  echo "wayland_set=$([ -n "${WAYLAND_DISPLAY:-}" ] && echo yes || echo no)"
  echo "xdg_session_type=${XDG_SESSION_TYPE:-}"
  echo "driver_version=$("$BIN" --version 2>/dev/null)"
  echo "driver_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
  echo "python=$("$JEV/.venv/bin/python" --version 2>&1)"
  echo "mcp=$("$JEV/.venv/bin/python" -c 'import importlib.metadata as m; print(m.version("mcp"))')"
  echo "anyio=$("$JEV/.venv/bin/python" -c 'import importlib.metadata as m; print(m.version("anyio"))')"
  echo "started_utc=$(date -u +%FT%TZ)"
} > "$OUT/session-env.txt"
"$JEV/.venv/bin/python" "$HERE/run_trials.py" --jev-root "$JEV" --driver-bin "$BIN" --out "$OUT" --tmp "$TMP" "$@"
rc=$?
echo "finished_utc=$(date -u +%FT%TZ) rc=$rc" >> "$OUT/session-env.txt"
exit $rc
