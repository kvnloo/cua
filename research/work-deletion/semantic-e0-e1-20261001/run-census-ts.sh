#!/bin/bash
set -uo pipefail
BIN=/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-a0bca7440
WRAP=/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-a0bca7440-e2e
OUT=/mnt/zer0models/github/cua-lanes/speed-frontier/research/work-deletion/semantic-e0-e1-20261001
JEV=/mnt/zer0models/github/cua-lanes/p0-4316-v3/libs/cua-driver/examples/jev-use
PY="$JEV/.venv/bin/python"
export PATH="/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin:/home/kvn/.local/bin:$PATH"
export CUA_DRIVER_BIN="$WRAP"
export CUA_DRIVER_PERMISSION_MODE=unrestricted
export CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1
cat > "$WRAP" <<WRAP
#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec $(printf '%q' "$BIN") "\$@"
WRAP
chmod 700 "$WRAP"
echo "atspi=${AT_SPI_BUS_ADDRESS:-missing} display=${DISPLAY:-} hyprland=${HYPRLAND_INSTANCE_SIGNATURE:-}"
"$PY" "$OUT/census_e1.py" --receipt "$OUT/receipt.json" --repeats 5
census_rc=$?
cd "$JEV"
"$PY" verify_setup.py --typescript --guarded-completion --output-dir "$OUT/guarded-accepted-ts" > "$OUT/guarded-accepted-ts.log" 2>&1
ts_acc=$?
"$PY" verify_setup.py --typescript --guarded-completion --guarded-completion-decline --output-dir "$OUT/guarded-decline-ts" > "$OUT/guarded-decline-ts.log" 2>&1
ts_dec=$?
printf 'census=%s ts_accepted=%s ts_decline=%s\n' "$census_rc" "$ts_acc" "$ts_dec" | tee "$OUT/rcs-rerun.txt"
exit $((census_rc || ts_acc || ts_dec))
