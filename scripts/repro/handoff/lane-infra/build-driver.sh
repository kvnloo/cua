#!/usr/bin/env bash
# usage: build-driver.sh <worktree-dir> <label> [target-dir-name]
# Builds the exact CI candidate: cargo build --locked --release -p cua-driver --features portal-input
# with CI-default profile settings (no user-global panic=abort / thin-LTO / target-cpu=native overrides).
set -euo pipefail
WT="$1"; LABEL="$2"; TGT="${3:-cua-release}"
L=/mnt/zer0models/github/cua-lanes
export CARGO_HOME=/mnt/zer0models/cargo-home-cua
export CARGO_TARGET_DIR=/mnt/zer0models/cargo-targets/$TGT
export TMPDIR=/mnt/zer0models/cua-lane-tmp
export PATH=/home/kvn/.cargo/bin:$PATH
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
LOG="$L/logs/cargo-build-$LABEL.log"
cd "$WT"
# Shared CARGO_TARGET_DIR + separate worktrees: cargo freshness is mtime-based and workspace-member
# metadata hashes are path-independent, so a worktree whose files are OLDER than the cached outputs is
# treated as "Fresh" even when its contents differ (this produced a stale #4318 binary on the first try).
# Touch every Rust-workspace file so the workspace crates are recompiled from THIS worktree's sources.
find libs/cua-driver/rust -path libs/cua-driver/rust/target -prune -o -type f -exec touch {} +
echo "[$(date -u +%FT%TZ)] build start label=$LABEL head=$(git rev-parse HEAD) rustc=$(rustc --version)"
start=$(date +%s)
nice -n 10 cargo build -v --locked --release -p cua-driver --features portal-input \
  --manifest-path libs/cua-driver/rust/Cargo.toml -j 8 > "$LOG" 2>&1
end=$(date +%s)
for crate in cua_driver cua_driver_core cua_driver_contract platform_linux; do
  ran=$(grep -c -E "Running .*--crate-name ${crate} " "$LOG" || true)
  echo "  crate ${crate}: rustc invocations this run = ${ran}"
done
echo "  Fresh workspace units: $(grep -c -E 'Fresh (cua-driver|cua-driver-core|cua-driver-contract|platform-linux) ' "$LOG" || true)"
cp "$CARGO_TARGET_DIR/release/cua-driver" "$L/bin/cua-driver-$LABEL"
echo "[$(date -u +%FT%TZ)] build done label=$LABEL seconds=$((end-start)) sha256=$(sha256sum "$L/bin/cua-driver-$LABEL" | cut -d' ' -f1)"
"$L/bin/cua-driver-$LABEL" --version || true
