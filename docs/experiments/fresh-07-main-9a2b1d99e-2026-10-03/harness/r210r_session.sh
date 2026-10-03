#!/usr/bin/env bash
# FRESH-07: in-session entry for the R2-10R rows (inside hostless -> fresh07_chunks.sh -> cua-x11-session.sh).
# Same refusals as orig/r2-10r/harness/in_session.sh, then calls the ORIGINAL harness unchanged:
#   r210r_session.sh <wt> rounds <driver> <out> <soft-cap-s> <round>...   scripted plan, one round per call
#   r210r_session.sh <wt> once <done-file> <python-script> [args...]      one call (smoke, toolslist, native block)
# Load rule: a round (or the single call) starts only at 1-min loadavg <= 4.0; else re-read every second
# for up to 60 s, then exit 75. Soft cap: no new round after <soft-cap-s>, exit 76. A round is DONE
# (marker file) only when the harness exits 0; otherwise it is kept and re-run later.
set -uo pipefail
WT="$1"; MODE="$2"; shift 2
refuse() { echo "refusing: $*" >&2; exit 96; }
[ -n "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || refuse "not inside the isolated X11 session"
[ "${R2_10_OUTER_HOSTLESS:-0}" = "1" ] || refuse "caller is not under hostless"
case "${XDG_RUNTIME_DIR:-}" in "$(dirname "$TMPDIR")"/*) ;; *) refuse "XDG_RUNTIME_DIR not private" ;; esac
case "${DBUS_SESSION_BUS_ADDRESS:-}" in *"/run/user/"*) refuse "host session bus" ;; esac
for v in CUA_DRIVER_PERMISSION_MODE CUA_DRIVER_DANGEROUSLY_BYPASS_APPROVALS CUA_E2E_BROWSER_NO_SANDBOX TYPESAFE_API_KEY; do
  [ -z "${!v:-}" ] || refuse "$v set"
done
xdpyinfo >/dev/null 2>&1 || { echo "[fresh07] session_failed_to_start: display unreachable" >&2; exit 97; }
HERE="$(cd "$(dirname "$0")" && pwd)"; H="$HERE/../orig/r2-10r/harness"
EX="$WT/libs/cua-driver/examples/jev-use"; PY="$EX/.venv/bin/python"
export JEV_USE_DIR="$EX" PYTHONDONTWRITEBYTECODE=1
load_gate() {
  local i l
  # Non-timing calls (default-off smoke, tools/list) pass FRESH07_NO_LOAD_GATE=1: the load rule is a
  # timing rule. The load is still recorded.
  if [ "${FRESH07_NO_LOAD_GATE:-0}" = 1 ]; then
    echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"load1\":$(cut -d' ' -f1 /proc/loadavg),\"gate\":\"off (non-timing)\"}" >> "$GATE_LOG"; return 0
  fi
  for i in $(seq 0 60); do
    l=$(cut -d' ' -f1 /proc/loadavg)
    if awk -v l="$l" 'BEGIN{exit !(l <= 4.0)}'; then echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"waited_s\":$i,\"load1\":$l,\"ok\":true}" >> "$GATE_LOG"; return 0; fi
    sleep 1
  done
  echo "{\"t\":\"$(date -u +%FT%T.%3NZ)\",\"what\":\"$1\",\"waited_s\":60,\"load1\":$l,\"ok\":false}" >> "$GATE_LOG"; return 1
}
echo "[fresh07] display_set=yes loadavg=$(cut -d' ' -f1-3 /proc/loadavg) atspi=${CUA_SESSION_ATSPI:-0} mode=$MODE"
if [ "$MODE" = rounds ]; then
  DRV="$1"; OUT="$2"; CAP="$3"; shift 3
  mkdir -p "$OUT/rounds"; GATE_LOG="$OUT/load-gate.jsonl"; t0=$(date +%s)
  for r in "$@"; do
    rr=$(printf %02d "$r"); [ -e "$OUT/rounds/r$rr.DONE" ] && continue
    [ $(( $(date +%s) - t0 )) -gt "$CAP" ] && { echo "[fresh07] soft cap reached before round $rr"; exit 76; }
    load_gate "round $rr" || { echo "[fresh07] load rule: round $rr not started"; exit 75; }
    n=0; pre="S-r$rr-"; while [ -e "$OUT/run-manifest-$pre.json" ]; do n=$((n + 1)); pre="S-r$rr-a$n-"; done
    "$PY" "$H/r2_10_browser.py" --driver "$DRV" --out "$OUT" --plan scripted --arms BASE,COMP,COMP_K,COMP_E \
      --start-round "$r" --rounds 1 --prefix "$pre"
    rc=$?; echo "[fresh07] round $rr prefix=$pre rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
    [ "$rc" -eq 0 ] && : > "$OUT/rounds/r$rr.DONE"
  done
  exit 0
fi
if [ "$MODE" = once ]; then
  DONEF="$1"; SCRIPT="$2"; shift 2
  [ -e "$DONEF" ] && exit 0
  mkdir -p "$(dirname "$DONEF")"; GATE_LOG="$(dirname "$DONEF")/load-gate.jsonl"
  load_gate "$(basename "$DONEF")" || exit 75
  "$PY" "$H/$SCRIPT" "$@"; rc=$?
  echo "[fresh07] once $(basename "$DONEF") rc=$rc loadavg=$(cut -d' ' -f1-3 /proc/loadavg)"
  [ "$rc" -eq 0 ] && : > "$DONEF"
  exit "$rc"
fi
refuse "unknown mode $MODE"
