#!/usr/bin/env bash
# STEP 0 compatibility smoke (always via cua-x11-session.sh):
#   step0_smoke.sh <worktree> <driver-bin> <outdir>
# Two unmodified run.py mock runs against the pinned Driver: plain and --guarded-completion.
set -uo pipefail
WT="$1"; DRV="$2"; OUT="$3"
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || { echo "refusing: not inside isolated X11 session" >&2; exit 97; }
mkdir -p "$OUT"
export CUA_DRIVER_BIN="$DRV"
EX="$WT/libs/cua-driver/examples/jev-use"
cd "$EX"
echo "driver_version=$("$DRV" --version 2>&1 | head -1)"
.venv/bin/python fixture_server.py --port 0 > "$OUT/fixture.out" 2>&1 &
FX=$!
for _ in $(seq 50); do grep -q "Fixture ready" "$OUT/fixture.out" 2>/dev/null && break; sleep 0.1; done
URL=$(sed -n 's/^Fixture ready at //p' "$OUT/fixture.out")
for arm in plain guarded; do
  flags=(); [ "$arm" = guarded ] && flags=(--guarded-completion)
  .venv/bin/python python/run.py --provider mock --fixture-url "$URL" --token "r2-07-step0-$arm" \
    --log "$OUT/$arm.jsonl" "${flags[@]}" > "$OUT/$arm.stdout" 2> "$OUT/$arm.stderr"
  rc=$?
  state=$(.venv/bin/python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('${URL}state')))")
  echo "arm=$arm rc=$rc state=$state"
done
kill $FX
