#!/usr/bin/env bash
# render.sh <default_lockdir> <outdir>: render the templated scripts with a default lock dir.
#   <outdir>/quiet-timed, quiet-shared, quiet-holders  (v2, INFRA-08)
#   <outdir>/v1/quiet-timed                            (v1, as installed before INFRA-08)
# The packet commits templates only (placeholder @QUIET_LANE_DEFAULT_LOCKDIR@), never a local path.
set -euo pipefail
default="$1"; out="$2"; src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts"
case "$default" in *'|'*|*'&'*|*\\*) echo "render.sh: unsupported character in lock dir" >&2; exit 64;; esac
mkdir -p "$out/v1"
for f in quiet-timed quiet-shared quiet-holders v1/quiet-timed; do
  sed "s|@QUIET_LANE_DEFAULT_LOCKDIR@|$default|" "$src/$f" > "$out/$f.tmp"; chmod 755 "$out/$f.tmp"; mv "$out/$f.tmp" "$out/$f"
done
