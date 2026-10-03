#!/usr/bin/env bash
# FIX-03 unit evidence on the final F5 branch head and the red trees (under hostless).
# Each cargo step is its own cargo-lock acquisition + private X11 session.
set -uo pipefail
L=<scrubbed1>; U=<scrubbed0>/w6-fix03/units; O=<scrubbed0>/w6-fix03/unit-out-final
WT=$L/w6-fix03
$U/run_unit.sh $L/w6-fix03-red1 $O/red-FS core-f4-toctou -p cua-driver-core --lib set_input_files
$U/run_unit.sh $L/w6-fix03-red2 $O/red-U linux-recording-lookup -p platform-linux --lib recording_element_lookup
$U/run_unit.sh $WT $O/green-F5 core-lib-tests -p cua-driver-core --lib --tests --no-fail-fast
$U/run_unit.sh $WT $O/green-F5 platform-linux-lib -p platform-linux --lib --no-fail-fast
mkdir -p $O/green-F5/jev-use
CUA_SESSION_EXTRA_ENV="CUA_DRIVER_RS_TELEMETRY_ENABLED=false DO_NOT_TRACK=1" \
  $L/cua-x11-session.sh $L/run-unit.sh $WT $O/green-F5/jev-use > $O/green-F5/jev-use.session.log 2>&1
echo "jev-use rc=$?" >> $O/green-F5/steps.txt
echo chain-final-done
