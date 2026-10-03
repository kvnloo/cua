#!/usr/bin/env bash
# usage (on the host, through hostless + hostless-strict, under the cargo-build lock):
#   unit_red_green.sh <worktree> <lanes-dir> <fix-only.patch> <cargo-home> <target-dir> <rustup-home>
# The red/green pair on the committed G head:
#   red   = HEAD with only the fix hunk reverse-applied (git apply -R fix-only.patch): the settle loop
#           extraction and both new tests stay; the deadline-exit final read is gone;
#   green = HEAD (the fix commit) after `git checkout -- <file>` restores the file (checked by sha256).
# Each phase runs unit_in_session.sh inside its own private X11 session.
set -uo pipefail
WT="$1"; LANES="$2"; PATCH="$3"; CH="$4"; TD="$5"; RH="$6"
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run through hostless" >&2; exit 96; }
HERE="$(cd "$(dirname "$0")" && pwd)"
F=libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs
cd "$WT"
head_sha="$(git rev-parse HEAD)"; want="$(git show HEAD:$F | sha256sum | cut -d' ' -f1)"
session() { env CUA_SESSION_ATSPI=1 "CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 CUA_DRIVER_RS_TELEMETRY_ENABLED=0 DO_NOT_TRACK=1" \
  "$LANES/cua-x11-session.sh" "$HERE/unit_in_session.sh" "$WT" "$CH" "$TD" "$RH" "$1"; }
echo "=== red: HEAD $head_sha with fix-only.patch reverse-applied ($(sha256sum "$PATCH" | cut -c1-16))"
git apply -R "$PATCH" || { echo "reverse apply failed" >&2; exit 3; }
session red
git checkout -- "$F"
have="$(sha256sum "$F" | cut -d' ' -f1)"
[ "$have" = "$want" ] || { echo "restore failed: $have != $want" >&2; exit 4; }
echo "=== restored $F to HEAD (sha256 $have); worktree tracked changes: $(git status --porcelain --untracked-files=no | wc -l)"
echo "=== green: HEAD $head_sha"
session green
