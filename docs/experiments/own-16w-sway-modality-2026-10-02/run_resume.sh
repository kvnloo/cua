#!/usr/bin/env bash
# usage (under hostless): run_resume.sh <lanes-dir> <worktree> <U-driver> <F-driver> <tmp-root> <oracle-python> <MODE-BIN-ID>...
# Deviation D1 (README): the batch's own 2 h background limit killed it during SX-U-T2. This runs the
# remaining pre-registered sessions with the FROZEN definitions of run_batch.sh (its lines up to
# X11_ROWS=, evaluated unchanged), one session per argument, e.g. SX-U-T2:truth:3 X11-F-T2:truth:3:rows
# or SW-U-B1:timing:0 or SW-D1:smoke.
set -uo pipefail
PKT_DIR="$2/docs/experiments/own-16w-sway-modality-2026-10-02"
eval "$(sed -n '1,/^X11_ROWS=/p' "$PKT_DIR/run_batch.sh")"
shift 6
log "resume start: $*"
for spec in "$@"; do
  IFS=: read -r name kind rot rows <<< "$spec"
  IFS=- read -r mode bin id <<< "$name"
  case "$kind" in
    truth) if [ "${rows:-}" = rows ]; then session "$mode" "$bin" "$id" truth "$rot" --rows "$X11_ROWS"
           else session "$mode" "$bin" "$id" truth "$rot"; fi ;;
    timing) session "$mode" "$bin" "$id" timing "$rot" --pairs 21 ;;
    smoke)
      d="$OUT/SW/D1"; mkdir -p "$d"
      ( cd "$WT" && CUA_SESSION_ATSPI=1 CUA_SWAY_TIMEOUT=900 CUA_SESSION_EXTRA_ENV="CUA_SESSION_ATSPI=1 $BASE_ENV" \
          "$QT" own16w-SW-D1 "$LANES/cua-sway-session.sh" "$PKT/run_in_session.sh" "$WT" "$U" "$d/raw" "$d/work" \
          --env-mode sway-wayland --mode smoke --label SW-D1 --binary-tag U --alt-driver "$F" > "$d/session.log" 2>&1 )
      log "SW-D1 rc=$?" ;;
    *) echo "bad spec $spec" >&2; exit 2 ;;
  esac
done
log "resume done: $*"
