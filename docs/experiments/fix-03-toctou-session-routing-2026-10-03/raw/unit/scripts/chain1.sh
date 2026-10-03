#!/usr/bin/env bash
# chain 1 (under hostless): F5-pre build, then red/green filtered unit steps, each its own cargo-lock acquisition
set -uo pipefail
L=<scrubbed1>; U=<scrubbed0>/w6-fix03/units; O=<scrubbed0>/w6-fix03/unit-out
<scrubbed0>/w6-fix03/builds/build.sh $L/w6-fix03-f5wip fix03-f5pre-ea12e6f86
$U/run_unit.sh $L/w6-fix03-red1 $O/red1 core-f4-toctou -p cua-driver-core --lib set_input_files
$U/run_unit.sh $L/w6-fix03-red1 $O/red1 linux-routing -p platform-linux --lib snapshot_routing
$U/run_unit.sh $L/w6-fix03-red2 $O/red2 linux-recording-lookup -p platform-linux --lib recording_element_lookup
$U/run_unit.sh $L/w6-fix03-f5wip $O/green-wip core-f4-toctou -p cua-driver-core --lib set_input_files
$U/run_unit.sh $L/w6-fix03-f5wip $O/green-wip linux-routing-and-lookup -p platform-linux --lib -- snapshot_routing recording_element_lookup
echo chain1-done
