#!/usr/bin/env bash
# Inputs must already be available. No download/install step.
set -uo pipefail
if [[ $# != 3 ]]; then echo "Usage: reproduce.sh SOURCE PYTHON NEW_OUTPUT" >&2; exit 2; fi
SOURCE=$1
PYTHON=$2
OUTPUT=$3
PACKET=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -e "$OUTPUT" || -L "$OUTPUT" ]]; then echo "Output must not exist: $OUTPUT" >&2; exit 2; fi
mkdir -p "$OUTPUT" || exit 2
OUTPUT=$(cd -- "$OUTPUT" && pwd)
for phase in characterize proposed-parity; do
  mkdir -p "$OUTPUT/$phase/home"
  env -i HOME="$OUTPUT/$phase/home" PATH="$(dirname -- "$PYTHON"):/usr/bin:/bin" \
    LANG=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_NO_LAZY_FETCH=1 GIT_OPTIONAL_LOCKS=0 \
    "$PYTHON" -I "$PACKET/run.py" --source "$SOURCE" --output "$OUTPUT/$phase" --phase "$phase" \
    2>&1 | tee "$OUTPUT/$phase/stdout.log"
  result=${PIPESTATUS[0]}
  printf '%s\n' "$result" > "$OUTPUT/$phase/exit-status.txt"
  expected=0
  if [[ "$phase" == proposed-parity ]]; then expected=1; fi
  if [[ "$result" != "$expected" ]]; then
    printf 'Unexpected %s exit: %s (expected %s)\n' "$phase" "$result" "$expected" >&2
    exit 2
  fi
done

