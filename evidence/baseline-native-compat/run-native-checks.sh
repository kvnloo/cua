#!/bin/sh
set -eu
root=/workspace/shared/cua-baseline-native-compat
repo="$root/repo"
evidence="$repo/evidence/baseline-native-compat"
export LD_LIBRARY_PATH="$root/sysroot/usr/lib/x86_64-linux-gnu"
export CUA_DRIVER_REQUIRE_UNIFFI=1
export PYTHONPATH=src
cp "$root/target-baseline/debug/libcua_driver_sdk.so" "$repo/libs/cua-driver/python/src/cua_driver/libcua_driver_sdk.so"
sha256sum "$root/target-baseline/debug/libcua_driver_sdk.so" "$repo/libs/cua-driver/python/src/cua_driver/libcua_driver_sdk.so" > "$evidence/native-library-sha256.txt"
ldd "$root/target-baseline/debug/libcua_driver_sdk.so" > "$evidence/native-library-ldd.txt"
cd "$repo/libs/cua-driver/python"
python3 -m unittest tests/test_uniffi_loader.py tests/test_remote_channel.py tests/test_cursor_motion.py -v > "$evidence/native-tests.log" 2>&1
python3 "$evidence/baseline_native_probe.py" > "$evidence/native-probe-results.json"
