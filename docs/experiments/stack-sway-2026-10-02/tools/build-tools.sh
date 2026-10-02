#!/usr/bin/env bash
# build-tools.sh <kit-dir> <wlroots-src-dir>   (run under hostless)
# Builds landlock-scope, seatctl, seatprobe into <kit-dir>/bin from the sources next to this script.
# Protocol XMLs: xdg-shell from the system wayland-protocols, wlr-virtual-pointer + virtual-keyboard
# from the wlroots 0.20.2 source tree (same protocols the kit's libwlroots implements).
set -euo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
KIT="$1"; WLR="$2"; SRC="$(cd "$(dirname "$0")" && pwd)"
B="$KIT/build"; mkdir -p "$B" "$KIT/bin"
gen() { wayland-scanner client-header "$1" "$B/$2-client-protocol.h"; wayland-scanner private-code "$1" "$B/$2-protocol.c"; }
gen /usr/share/wayland-protocols/stable/xdg-shell/xdg-shell.xml xdg-shell
gen "$WLR/protocol/wlr-virtual-pointer-unstable-v1.xml" wlr-virtual-pointer-unstable-v1
gen "$WLR/protocol/virtual-keyboard-unstable-v1.xml" virtual-keyboard-unstable-v1
CF="-O2 -Wall -Wextra -Werror=implicit-function-declaration -I$B"
cc $CF -o "$KIT/bin/landlock-scope" "$SRC/landlock-scope.c"
cc $CF -o "$KIT/bin/seatctl" "$SRC/seatctl.c" "$B/wlr-virtual-pointer-unstable-v1-protocol.c" \
   "$B/virtual-keyboard-unstable-v1-protocol.c" $(pkg-config --cflags --libs wayland-client xkbcommon)
cc $CF -o "$KIT/bin/seatprobe" "$SRC/seatprobe.c" "$B/xdg-shell-protocol.c" \
   $(pkg-config --cflags --libs wayland-client xkbcommon)
sha256sum "$KIT/bin/landlock-scope" "$KIT/bin/seatctl" "$KIT/bin/seatprobe"
