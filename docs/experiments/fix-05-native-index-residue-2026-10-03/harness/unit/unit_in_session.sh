#!/usr/bin/env bash
# FIX-05 unit runner (copy of FIX-04 harness/unit/unit_in_session.sh), INSIDE cua-x11-session.sh (caller: hostless -> cargo lock -> timeout 1200 -> session).
# usage: unit_in_session.sh <worktree> <outdir> <step-name> <cargo test args...>
# Refuses outside a private X11 session. Touches the worktree's Rust files so the shared target dir
# recompiles the workspace crates from THIS worktree (see build-driver.sh).
set -uo pipefail
WT="$1"; OUT="$2"; NAME="$3"; shift 3
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] \
  || { echo "refusing: not inside the private X11 session" >&2; exit 97; }
xdpyinfo > /dev/null 2>&1 || { echo "[probe] xdpyinfo FAILED" >&2; exit 95; }
mkdir -p "$OUT"
export CARGO_TARGET_DIR="${FX_TARGET:?}"
export PATH="$CARGO_HOME/bin:$RUSTUP_HOME/../.cargo/bin:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT"
find libs/cua-driver/rust -path libs/cua-driver/rust/target -prune -o -type f -exec touch {} +
{ echo "head=$(git rev-parse HEAD) dirty=$(git status --porcelain -- libs/cua-driver | tr '\n' ';')"
  echo "rustc=$(rustc --version) display_private=yes started=$(date -u +%FT%TZ)"
  echo "cmd=cargo test --locked $*"; } > "$OUT/$NAME.env"
t0=$(date +%s)
nice -n 10 cargo test --locked --manifest-path libs/cua-driver/rust/Cargo.toml -j 8 "$@" > "$OUT/$NAME.log" 2>&1
rc=$?
echo "rc=$rc seconds=$(( $(date +%s) - t0 )) ended=$(date -u +%FT%TZ)" >> "$OUT/$NAME.env"
exit $rc
