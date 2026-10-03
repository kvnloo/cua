#!/usr/bin/env bash
# Lane-local driver for PREREG's band-extension rule (rounds 7..10 per task, one round at a time;
# stop a task after the first round in which both arms have >= 20 valid band steals).
# usage: hostless hostless-strict env ... band_ext.sh (run from the lanes dir)
set -uo pipefail
T=<tmp>
P=<lanes>/w4-a2-own20g/docs/experiments/own-20g-guard-final-diff-2026-10-03
L=<lanes>
U=$L/bin/cua-driver-own20g-a2-u-bdf33d9fe; S=f0fe3219e5e0d4227d57128f3f4f2c487f54462d206d0fbe3ea9317c56eb41eb
G=$L/bin/cua-driver-own20g-a2-g-a30cbbc3b; SG=66e303c7167d6bd912b628f5d2558f9fafa6695bb1b7cafdafba2914595aa6ff
valid() {  # $1 = task letter c|t -> prints "minvalid"
  rm -rf "$T/ext-scratch/raw"; mkdir -p "$T/ext-scratch"; cp "$P/package.py" "$P/analyze.py" "$T/ext-scratch/"
  ( cd "$T/ext-scratch" && python3 package.py --runs "$T/runs" --global-ledger "$T/../locks/quiet-lane-ledger.jsonl" \
      --label-prefix own20g- --scrub "$T=<tmp>" >/dev/null && python3 analyze.py --raw raw --out s.json --metrics m.jsonl.gz >/dev/null \
    && python3 -c 'import json,sys; g=json.load(open("s.json"))["r2"]["groups"]; t={"c":("checkbox","S0"),"t":("text","X")}[sys.argv[1]]; print(min(g[f"{t[0]}/{a}/band"]["valid"] for a in (t[1], t[1]+"+CL")))' "$1" )
}
for task in c t; do
  for r in 07 08 09 10; do
    v=$(valid $task); echo "[$(date -u +%FT%T.%3NZ)] task=$task before round $r: min valid band = $v"
    [ "$v" -ge 20 ] && { echo "task=$task: rule satisfied, stop"; break; }
    env OWN20G_LANES=$L "$P/run_all.sh" $L/w4-a2-own20g $U $S $G $SG "$P/plan.json" "$T/runs" "$T" own20g "x${task}${r}"
  done
  v=$(valid $task); echo "[$(date -u +%FT%T.%3NZ)] task=$task final min valid band = $v"
done
