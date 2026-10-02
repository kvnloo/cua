#!/usr/bin/env bash
# Runs inside cua-x11-session.sh (private rootless Xvfb + private dbus, scrubbed env).
#   usage: session_entry.sh <worktree> <base-jev-root> <driver-bin> <out-dir> <tmp-dir> <block-label> [run_trials args...]
set -uo pipefail
if [ -n "${WAYLAND_DISPLAY:-}" ] || env | grep -q '^HYPRLAND_'; then
  echo "refusing: host Wayland/Hyprland variables present" >&2; exit 97
fi
WT="$1"; BASEJEV="$2"; BIN="$3"; OUT="$4"; TMP="$5"; BLOCK="$6"; shift 6
JEV="$WT/libs/cua-driver/examples/jev-use"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT" "$TMP"
ENVF="$OUT/session-env-$BLOCK.txt"
{
  echo "display_set=$([ -n "${DISPLAY:-}" ] && echo yes || echo no)"
  echo "wayland_set=$([ -n "${WAYLAND_DISPLAY:-}" ] && echo yes || echo no)"
  echo "hyprland_vars=$(env | grep -c '^HYPRLAND_')"
  echo "xdg_session_type=${XDG_SESSION_TYPE:-}"
  echo "driver_version=$("$BIN" --version 2>/dev/null)"
  echo "driver_sha256=$(sha256sum "$BIN" | cut -d' ' -f1)"
  echo "worktree_head=$(git -C "$WT" rev-parse HEAD)"
  echo "worktree_dirty_jev_use=$(git -C "$WT" status --porcelain -- libs/cua-driver/examples/jev-use | wc -l)"
  echo "base_run_py_sha256=$(sha256sum "$BASEJEV/python/run.py" | cut -d' ' -f1)"
  echo "fixed_run_py_sha256=$(sha256sum "$JEV/python/run.py" | cut -d' ' -f1)"
  echo "fixed_run_ts_sha256=$(sha256sum "$JEV/typescript/run.ts" | cut -d' ' -f1)"
  echo "python=$("$JEV/.venv/bin/python" --version 2>&1)"
  echo "mcp=$("$JEV/.venv/bin/python" -c 'import importlib.metadata as m; print(m.version("mcp"))')"
  echo "anyio=$("$JEV/.venv/bin/python" -c 'import importlib.metadata as m; print(m.version("anyio"))')"
  echo "node=$(node --version)"
  echo "ts_sdk=$(node -p "require('$JEV/node_modules/@modelcontextprotocol/sdk/package.json').version")"
  echo "loadavg_start=$(cut -d' ' -f1-3 /proc/loadavg)"
  echo "started_utc=$(date -u +%FT%TZ)"
} > "$ENVF"
"$JEV/.venv/bin/python" "$HERE/run_trials.py" --jev-root "$JEV" --base-jev-root "$BASEJEV" \
  --driver-bin "$BIN" --out "$OUT" --tmp "$TMP" "$@"
rc=$?
echo "finished_utc=$(date -u +%FT%TZ) rc=$rc" >> "$ENVF"
exit $rc
