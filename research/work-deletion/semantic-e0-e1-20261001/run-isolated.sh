#!/bin/bash
# Isolated-session runner. Caller must already be inside cua-x11-session.sh.
set -uo pipefail
HEAD=a0bca744067d04f05904319d3d919be30c336556
BIN=/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-a0bca7440
WRAP=/mnt/zer0models/github/cua-lanes/bin/cua-driver-4316-a0bca7440-e2e
OUT=/mnt/zer0models/github/cua-lanes/speed-frontier/research/work-deletion/semantic-e0-e1-20261001
JEV=/mnt/zer0models/github/cua-lanes/p0-4316-v3/libs/cua-driver/examples/jev-use
PY="$JEV/.venv/bin/python"
export PATH="/home/kvn/.local/share/fnm/node-versions/v22.23.2/installation/bin:/home/kvn/.local/bin:$PATH"
export CUA_DRIVER_BIN="$WRAP"
export CUA_DRIVER_PERMISSION_MODE=unrestricted
export CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS=1
cat > "$WRAP" <<EOF
#!/bin/bash
export CUA_E2E_BROWSER_NO_SANDBOX=1
export CUA_E2E_BROWSER_STDERR=1
exec $(printf '%q' "$BIN") "\$@"
EOF
chmod 700 "$WRAP"
{
  echo "display=${DISPLAY:-}"
  echo "session_type=${XDG_SESSION_TYPE:-}"
  echo "hyprland=${HYPRLAND_INSTANCE_SIGNATURE:-}"
  echo "wayland=${WAYLAND_DISPLAY:-}"
  echo "driver_sha256=$(sha256sum "$BIN" | awk '{print $1}')"
  echo "driver_version=$("$BIN" --version 2>&1 | head -1)"
  echo "head=$HEAD"
} | tee "$OUT/session-env.txt"
echo '=== census ==='
"$PY" "$OUT/census_e1.py" --receipt "$OUT/receipt.json" --repeats 5
census_rc=$?
echo "census_rc=$census_rc"
echo '=== guarded accepted ==='
cd "$JEV"
"$PY" verify_setup.py --guarded-completion --output-dir "$OUT/guarded-accepted" > "$OUT/guarded-accepted.log" 2>&1
accepted_rc=$?
echo "accepted_rc=$accepted_rc"
echo '=== guarded decline ==='
"$PY" verify_setup.py --guarded-completion --guarded-completion-decline --output-dir "$OUT/guarded-decline" > "$OUT/guarded-decline.log" 2>&1
decline_rc=$?
echo "decline_rc=$decline_rc"
printf 'census=%s accepted=%s decline=%s\n' "$census_rc" "$accepted_rc" "$decline_rc" | tee "$OUT/rcs.txt"
exit $((census_rc || accepted_rc || decline_rc))
