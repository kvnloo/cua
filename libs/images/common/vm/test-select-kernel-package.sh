#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"

cat >"$tmp/bin/dpkg" <<'MOCK'
#!/bin/sh
[ "$1" = "--print-architecture" ] && echo "${TEST_ARCH:-arm64}"
MOCK
cat >"$tmp/bin/apt-cache" <<'MOCK'
#!/bin/sh
[ "$1" = madison ] || exit 1
printf '%s\n' \
  'linux-image-virtual | 6.8.0.147.147 | http://ports.ubuntu.com noble-updates/main arm64 Packages' \
  'linux-image-virtual | 6.8.0.146.146 | http://ports.ubuntu.com noble-security/main arm64 Packages' \
  'linux-image-virtual | 6.8.0.31.31 | http://ports.ubuntu.com noble/main arm64 Packages'
MOCK
cat >"$tmp/bin/apt-get" <<'MOCK'
#!/bin/sh
for argument in "$@"; do candidate="$argument"; done
case "$TEST_CASE" in
  current) [ "$candidate" = "linux-image-virtual" ] ;;
  fallback) [ "$candidate" = "linux-image-virtual=6.8.0.146.146" ] ;;
  unavailable) exit 1 ;;
esac
MOCK
chmod +x "$tmp/bin/"*

try_case() {
    local case_name="$1" arch="$2" expected="$3"
    local output
    if output="$(TEST_CASE="$case_name" TEST_ARCH="$arch" \
        PATH="$tmp/bin:$PATH" sh "$here/select-kernel-package.sh" 2>"$tmp/stderr")"; then
        [ "$expected" != failure ] || { echo "unexpected success: $case_name/$arch"; exit 1; }
        [ "$output" = "$expected" ] || { echo "unexpected selection: $output"; exit 1; }
    else
        [ "$expected" = failure ] || { echo "unexpected failure: $case_name/$arch"; cat "$tmp/stderr"; exit 1; }
    fi
}

try_case current arm64 linux-image-virtual
try_case fallback arm64 linux-image-virtual=6.8.0.146.146
try_case unavailable arm64 failure
try_case fallback amd64 failure
echo "kernel package selection: 4 scenarios passed"
