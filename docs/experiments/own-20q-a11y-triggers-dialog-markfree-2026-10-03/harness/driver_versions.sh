#!/usr/bin/env bash
# usage (inside hostless + cua-x11-session.sh): driver_versions.sh <driver> [<driver> ...]
# Prints name, sha256 and the Driver's own --version for each binary (read inside the session).
set -uo pipefail
for b in "$@"; do
  echo "$(basename "$b") sha256=$(sha256sum "$b" | cut -d' ' -f1) version=$("$b" --version 2>&1 | head -1)"
done
