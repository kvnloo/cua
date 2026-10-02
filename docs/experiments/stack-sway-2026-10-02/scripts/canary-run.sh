#!/usr/bin/env bash
# usage: hostless canary-run.sh <outdir> <host-hyprland-instance-sig> <host-hyprland-pid>
# Isolation canary for cua-sway-session.sh (reachability only: connect()+close(), no bytes sent).
#  1. decoy listeners bound OUTSIDE the session but inside hostless' private mounts (never the host):
#     a path socket mimicking the Hyprland layout under the hostless /run/user tmpfs, a path socket at
#     /tmp/.X11-unix/X9 (hostless tmpfs) and an abstract socket @<random>. Each decoy logs accepts.
#  2. control: probe the decoys from outside the session (no Landlock) -> must be REACHABLE.
#  3. inside the session: host targets must be unreachable, the exposed hypr-layout decoy reachable
#     (probe sensitivity), the abstract and /tmp decoys unreachable; private compositor reachable.
#  4. the decoys' own accept logs independently confirm which connects arrived in each phase.
set -euo pipefail
[ "${CUA_HOSTLESS:-}" = 1 ] || { echo "refusing: run under hostless" >&2; exit 97; }
OUT="$1"; SIG="$2"; HPID="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
C="$HERE/isolation_canary.py"
mkdir -p "$OUT"
NAME="cua-canary-decoy-$RANDOM$RANDOM"
DH="/run/user/$(id -u)/hypr/CUADECOY$RANDOM/.socket.sock"
DX="/tmp/.X11-unix/X9"
/usr/bin/python3 "$C" decoy --dir "$OUT/decoy" --abstract "$NAME" --paths "$DH,$DX" --seconds 180 &
DP=$!
for _ in $(seq 1 50); do [ -f "$OUT/decoy/ready" ] && break; sleep 0.1; done
t0=$(date +%s.%3N)
/usr/bin/python3 "$C" control --abstract "$NAME" --paths "$DH,$DX" --out "$OUT/control.json"
sleep 0.3
PRE_ABS="$(/usr/bin/python3 "$C" list-abstract)"   # passive /proc/net/unix read before the session
echo "$PRE_ABS" > "$OUT/pre-abstract-x11.txt"
t1=$(date +%s.%3N)
set +e
CUA_SWAY_SEATS=1 CUA_SWAY_OUTPUTS=1280x720 CUA_SWAY_TIMEOUT=120 \
  <LANES>/cua-sway-session.sh /usr/bin/python3 "$C" inside --abstract "$NAME" \
  --decoy-paths "$DH,$DX" --host-sig "$SIG" --host-pid "$HPID" --pre-abstract "$PRE_ABS" --out "$OUT/inside.json"
inside_rc=$?
set -e
sleep 0.3
t2=$(date +%s.%3N)
kill "$DP" 2>/dev/null; wait "$DP" 2>/dev/null || true
/usr/bin/python3 - "$OUT" "$t0" "$t1" "$t2" "$DH" "$DX" "$NAME" "$inside_rc" <<'PY'
import json, sys
out, t0, t1, t2, dh, dx, name, inside_rc = sys.argv[1], *map(float, sys.argv[2:5]), *sys.argv[5:8], int(sys.argv[8])
acc = [json.loads(l) for l in open(f"{out}/decoy/accepts.jsonl")] if __import__("os").path.exists(f"{out}/decoy/accepts.jsonl") else []
def n(lo, hi, d): return sum(1 for a in acc if lo <= a["t"] < hi and a["decoy"] == d)
oracle = {
  "control_phase": {"hypr_decoy": n(t0, t1, dh), "x11_tmp_decoy": n(t0, t1, dx), "abstract_decoy": n(t0, t1, "@" + name)},
  "inside_phase": {"hypr_decoy": n(t1, t2, dh), "x11_tmp_decoy": n(t1, t2, dx), "abstract_decoy": n(t1, t2, "@" + name)},
}
want = {"control_phase": {"hypr_decoy": 1, "x11_tmp_decoy": 1, "abstract_decoy": 1},
        "inside_phase": {"hypr_decoy": 1, "x11_tmp_decoy": 0, "abstract_decoy": 0}}
control = json.load(open(f"{out}/control.json"))
inside = json.load(open(f"{out}/inside.json"))
res = {"schema": "cua.stack.sway.canary.v1", "evidence_class": "REAL",
       "control_all_reachable": all(r["result"] == "REACHABLE" for r in control["rows"]),
       "inside_pass": inside["pass"], "inside_rc": inside_rc,
       "decoy_accept_oracle": oracle, "decoy_accept_expected": want, "decoy_oracle_pass": oracle == want}
res["result"] = "PASS" if res["control_all_reachable"] and res["inside_pass"] and res["decoy_oracle_pass"] else "FAIL"
json.dump(res, open(f"{out}/summary.json", "w"), indent=1)
print(json.dumps(res, indent=1))
PY
