#!/usr/bin/env bash
# FRESH-07R covariate wrapper (inside the private X11 session only):
#   with_overlay_watch.sh <out-dir> <python> -- <command...>
# Starts overlay_watch.py (passive SubstructureNotify log of override-redirect map/unmap events) before the
# command, waits for its "ready" line, runs the command unchanged, then stops the watcher it started (SIGTERM to
# its own child only). Exits with the command's exit code. The watcher's output is one file per call:
# <out-dir>/overlay-<UTC>-<pid>.jsonl.
set -uo pipefail
OUT="$1"; PY="$2"; shift 2; [ "$1" = "--" ] && shift
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not inside the private X11 session" >&2; exit 97; }
mkdir -p "$OUT"; f="$OUT/overlay-$(date -u +%Y%m%dT%H%M%SZ)-$$.jsonl"
HERE="$(cd "$(dirname "$0")" && pwd)"
"$PY" "$HERE/overlay_watch.py" "$f" & wp=$!
for _ in $(seq 1 50); do grep -q '"ev": "ready"' "$f" 2>/dev/null && break; sleep 0.1; done
grep -q '"ev": "ready"' "$f" 2>/dev/null || echo "[overlay-watch] watcher not ready (kept running)" >&2
"$@"; rc=$?
kill -TERM "$wp" 2>/dev/null; wait "$wp" 2>/dev/null
echo "[overlay-watch] file=$(basename "$f") rows=$(wc -l < "$f" 2>/dev/null || echo 0) rc=$rc"
exit "$rc"
