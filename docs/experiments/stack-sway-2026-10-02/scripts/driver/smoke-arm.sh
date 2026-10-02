#!/usr/bin/env bash
# usage (inside cua-sway-session.sh): smoke-arm.sh <xwayland|native|default> <browser|atspi> <worktree> <driver-bin> <outdir>
# Runs the unchanged R2 smoke bodies (copies verified against artifacts/r2/SETUP.json sha256) in one arm:
#   xwayland: WAYLAND_DISPLAY removed -> X11 clients and the Driver's X11 backend over the private Xwayland
#   native:   WAYLAND_DISPLAY kept + CUA_DRIVER_RS_ENABLE_WAYLAND=1 -> Driver's native wlroots backend
#   default:  WAYLAND_DISPLAY kept, no opt-in (what a plain sway user gets)
# The R2 scripts' X11-only guard line is the only line removed for native/default; it is replaced by the
# private-session guard below.
set -uo pipefail
ARM="$1"; KIND="$2"; WT="$3"; DRV="$4"; OUT="$5"
case "${XDG_RUNTIME_DIR:-}" in <TMP>/sway-session.*) ;; *) echo "refusing: not in private sway session" >&2; exit 97;; esac
[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || exit 97
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/r2-smoke-copies/$KIND-smoke.sh"
mkdir -p "$(dirname "$OUT")"
case "$ARM" in
  xwayland) exec env -u WAYLAND_DISPLAY -u CUA_DRIVER_RS_ENABLE_WAYLAND bash "$SRC" "$WT" "$DRV" "$OUT" ;;
  native|default)
    BODY="$TMPDIR/$KIND-smoke-$ARM.sh"
    grep -v 'refusing: not inside isolated X11 session' "$SRC" > "$BODY"
    echo "== arm=$ARM removed_guard_lines=$(( $(wc -l < "$SRC") - $(wc -l < "$BODY") )) WAYLAND_DISPLAY=$WAYLAND_DISPLAY DISPLAY=$DISPLAY"
    if [ "$ARM" = native ]; then export CUA_DRIVER_RS_ENABLE_WAYLAND=1; else unset CUA_DRIVER_RS_ENABLE_WAYLAND; fi
    exec bash "$BODY" "$WT" "$DRV" "$OUT" ;;
  *) echo "bad arm" >&2; exit 2 ;;
esac
