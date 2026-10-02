#!/usr/bin/env bash
# Submits every calibration candidate through ar-submit (run under hostless).
set -euo pipefail
D=<tmp>/ar-calib; WT=<lanes>/ar-harness
export AR_REQUEST_DIR=$D/requests PYTHONDONTWRITEBYTECODE=1 TMPDIR=<tmp>
M=(--mechanism-start atspi_action/do_action_replied --mechanism-end atspi_action/post_sleep_done)
sub() { local name=$1; shift; echo "$name $(python3 $WT/harness/ar/ar-submit --branch ar/calib/$name "$@")"; }
sub sleep20 --hypothesis "Calibration known answer (REVERT): +20 ms sleep in the traced post-DoAction phase of perform_action_ref." "${M[@]}"
sub sleep50 --hypothesis "Calibration known answer (REVERT): +50 ms sleep in the traced post-DoAction phase of perform_action_ref." "${M[@]}"
sub delete50 --hypothesis "Calibration known answer (KEEP): removing the fixed 50 ms post-DoAction sleep in perform_action_ref shortens the GTK3 checkbox click by about 50 ms inside atspi_action." "${M[@]}"
sub success-early --hypothesis "Calibration known answer (G2 fail): perform_action_ref claims doAction was accepted without sending it." "${M[@]}"
for n in g0-frozen-item g0-test-item g0-trace-line g0-scanner; do
  sub $n --hypothesis "Calibration known answer (G0 fail): $n."
done
for i in 01 02 03 04 05 06 07 08 09 10; do
  sub noop$i --hypothesis "Calibration known answer (no KEEP): behaviour-neutral diff noop$i."
done
