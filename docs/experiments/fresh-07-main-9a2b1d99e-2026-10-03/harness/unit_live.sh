#!/usr/bin/env bash
# FRESH-07 Phase 1d (live X11 part): the three #[ignore]d overlay tests that need a live X server,
# one process each (the overlay owner is a process-wide OnceLock), inside the private Xvfb session.
# Run as: hostless flock <cargo-build.lock> flock -s <quiet-lane.lock> cua-x11-session.sh unit_live.sh <worktree> <out-dir>
# Machine paths come from the environment: CARGO_HOME, CARGO_TARGET_DIR, RUST_TOOLCHAIN_BIN.
set -uo pipefail
WT="$1"; OUT="$2"; mkdir -p "$OUT"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] || { echo "refusing: not inside the isolated X11 session" >&2; exit 97; }
: "${CARGO_HOME:?}" "${CARGO_TARGET_DIR:?}" "${RUST_TOOLCHAIN_BIN:?}"
export PATH="$RUST_TOOLCHAIN_BIN:$PATH"
unset RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
cd "$WT"
echo "head=$(git rev-parse HEAD) tree_rust=$(git rev-parse HEAD:libs/cua-driver/rust) start=$(date -u +%FT%TZ)" > "$OUT/live-env.txt"
: > "$OUT/live-steps.txt"
M=libs/cua-driver/rust/Cargo.toml
for t in x11_overlay_owner_stays_click_through_across_cursor_lifecycle_and_randr \
         x11_desktop_capture_hides_the_resting_overlay_and_restores_it \
         x11_overlay_input_shape_stays_empty_and_clicks_pass_through_after_resize; do
  timeout 1800 nice -n 10 cargo test --locked --manifest-path "$M" -p platform-linux --lib -j 8 \
    -- --ignored --exact "overlay::tests::$t" --test-threads=1 > "$OUT/live-$t.log" 2>&1
  echo "$t rc=$?" >> "$OUT/live-steps.txt"
done
cat "$OUT/live-steps.txt"
