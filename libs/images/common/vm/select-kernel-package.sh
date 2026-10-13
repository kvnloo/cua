#!/bin/sh
# APT mirrors can publish a new ARM64 kernel metapackage before all its
# matching linux-modules packages. Prefer the current kernel. When that
# dependency graph is incomplete, use only a resolvable update/security ABI.
# Never fall back to the unpatched base Noble kernel.
set -eu

pkg=linux-image-virtual
if apt-get -s -y --no-install-recommends install "$pkg" >/dev/null 2>&1; then
    printf '%s\n' "$pkg"
    exit 0
fi

if [ "$(dpkg --print-architecture)" != arm64 ]; then
    echo "kernel metapackage dependencies unresolved (not ARM64)" >&2
    exit 1
fi

versions="$(apt-cache madison "$pkg" |
    awk '/noble-(updates|security)/ { print $3 }' | sort -uVr)"
for version in $versions; do
    if apt-get -s -y --no-install-recommends install "$pkg=$version" >/dev/null 2>&1; then
        echo "ARM64 kernel archive incomplete; using resolvable $pkg=$version" >&2
        printf '%s\n' "$pkg=$version"
        exit 0
    fi
done

echo "No installable Ubuntu Noble update/security kernel on ARM64; refusing to build" >&2
exit 1
