#!/usr/bin/env bash
# G1 for each named calibration branch, sequentially (run under hostless):
#   build-driver.sh (flock cargo-build.lock, nice 19, target cua-release-ar) -> bin/cua-driver-ar-calib-<name>-<sha9>
#   cargo test --no-run (flock, nice 19, target ar-calib-test), then the lib tests inside a private session,
#   then g1_rows.py -> g1/<name>.rows.jsonl. Timing per step -> g1/timing.jsonl.
set -uo pipefail
D=<tmp>/ar-calib; L=<lanes>; WT=$L/ar-calib; H=$L/ar-harness
LOCK=<tmp>/locks/cargo-build.lock
export TMPDIR=<tmp> PYTHONDONTWRITEBYTECODE=1
ms() { date +%s%3N; }
for name in "$@"; do
  git -C $WT switch -q --detach ar/calib/$name || exit 1
  sha=$(git -C $WT rev-parse --short=9 HEAD); label=ar-calib-$name-$sha
  t0=$(ms)
  flock $LOCK nice -n 19 $L/build-driver.sh $WT $label cua-release-ar > $D/g1/$name.build.out 2>&1; brc=$?
  t1=$(ms)
  ( export CARGO_HOME=<mnt>/cargo-home-cua CARGO_TARGET_DIR=<mnt>/cargo-targets/ar-calib-test PATH=<home>/.cargo/bin:$PATH
    cd $WT/libs/cua-driver/rust && flock $LOCK nice -n 19 cargo test --locked --offline -j 6 --no-run -p cua-driver-core -p platform-linux --lib ) > $D/g1/$name.compile.log 2>&1; crc=$?
  t2=$(ms)
  env CUA_SESSION_ATSPI=1 CUA_SESSION_EXTRA_ENV=CUA_SESSION_ATSPI=1 $L/cua-x11-session.sh $D/g1/tests-in-session.sh > $D/g1/$name.tests.log 2>&1; trc=$?
  t3=$(ms)
  python3 $H/harness/ar/runner/g1_rows.py --build-out $D/g1/$name.build.out --test-log $D/g1/$name.tests.log --out $D/g1/$name.rows.jsonl > /dev/null
  printf '{"name":"%s","head":"%s","label":"%s","build_rc":%d,"compile_rc":%d,"session_rc":%d,"build_ms":%d,"test_compile_ms":%d,"test_run_ms":%d,"finished":"%s"}\n' \
    "$name" "$(git -C $WT rev-parse HEAD)" "$label" $brc $crc $trc $((t1-t0)) $((t2-t1)) $((t3-t2)) "$(date -u +%FT%TZ)" >> $D/g1/timing.jsonl
done
git -C $WT switch -q --detach 457bc65d45b2a87ac080b281ea777f8914002c29
