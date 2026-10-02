#!/usr/bin/env bash
# Runs the candidate worktree's crate lib tests inside the private X11+AT-SPI session (precompiled).
set -uo pipefail
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo refusing; exit 97; }
export CARGO_HOME=<mnt>/cargo-home-cua CARGO_TARGET_DIR=<mnt>/cargo-targets/ar-calib-test
export PATH=<home>/.cargo/bin:$PATH
cd <lanes>/ar-calib/libs/cua-driver/rust
echo "head=$(git rev-parse HEAD)"
for pkg in cua-driver-core platform-linux; do
  echo "### cargo test -p $pkg --lib"
  nice -n 19 cargo test --locked --offline -j 4 -p "$pkg" --lib 2>&1 | grep -E '^test result|FAILED|panicked|^error|^failures:|^    [a-z_:]+$'
  echo "rc=${PIPESTATUS[0]}"
done
