#!/bin/sh
set -eu
build_root=/workspace/scratch/cua-sdk-build
export CARGO_HOME="$build_root/cargo"
export RUSTUP_HOME="$build_root/rustup"
export CARGO_TARGET_DIR="$build_root/target-4888"
export CARGO_BUILD_JOBS=2
export CARGO_PROFILE_DEV_DEBUG=0
export PKG_CONFIG_SYSROOT_DIR="$build_root/sysroot"
export PKG_CONFIG_LIBDIR="$build_root/sysroot/usr/lib/x86_64-linux-gnu/pkgconfig:$build_root/sysroot/usr/share/pkgconfig"
export LD_LIBRARY_PATH="$build_root/sysroot/usr/lib/x86_64-linux-gnu"
export LIBRARY_PATH="$build_root/sysroot/usr/lib/x86_64-linux-gnu"
export PATH="$build_root/cargo/bin:$build_root/sysroot/usr/bin:$PATH"
cd /workspace/cua-compat-4888/libs/cua-driver/rust
exec cargo build --locked -p cua-driver-sdk --lib
