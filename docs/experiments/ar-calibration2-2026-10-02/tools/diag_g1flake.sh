#!/usr/bin/env bash
# DIAGNOSTIC, not a gate result (run under hostless, after the pre-registered calibration-2 run finished).
# The two calibration-2 G1 REJECTs (sleep20, noop05) failed one cua-driver-core history test each; both diffs
# touch only platform-linux/src/atspi/native.rs, so the core test binary is identical to the champion's.
#  1. reruns `cargo test -p cua-driver-core --lib` N times (lane-private target, nice 19, flock for any compile);
#  2. screens sleep20 and noop05 on their recorded G1 binaries with the pre-registered screen seeds, in one
#     quiet-timed block each, using tools/screen.py with G1 rows = recorded build row + recorded platform-linux
#     row + the first core rerun. Writes only under diag/g1flake/; never touches cal2-results.jsonl.
set -uo pipefail
D=<tmp>/ar-calib2; L=<lanes>; H=$L/ar-harness; A=$H/harness/ar
REPO=$L/ar-calib; CH=457bc65d45b2a87ac080b281ea777f8914002c29; HC=f56422868403857a032e069f33686efbbc0b48b6
TAU=$H/docs/experiments/ar-fix-2026-10-02/raw/aa/tau.json; CHAMP=$L/bin/cua-driver-ar-base-457bc65d4
LOCK=<tmp>/locks/cargo-build.lock
O=$D/diag/g1flake; mkdir -p $O
export TMPDIR=<tmp> PYTHONDONTWRITEBYTECODE=1 AR_LANES=$L
N=${N:-5}
[ "$(git -C $REPO rev-parse HEAD)" = $CH ] || { echo "ar-calib not at champion"; exit 2; }
( export CARGO_HOME=<mnt>/cargo-home-cua CARGO_TARGET_DIR=<mnt>/cargo-targets/ar-calib-test PATH=<home>/.cargo/bin:$PATH
  cd $REPO/libs/cua-driver/rust
  flock $LOCK nice -n 19 cargo test --locked --offline -j 4 --no-run -p cua-driver-core --lib > $O/core-compile.log 2>&1
  for k in $(seq 1 $N); do
    nice -n 19 cargo test --locked --offline -p cua-driver-core --lib > $O/core-run-$k.log 2>&1; rc=$?
    printf '{"run":%d,"rc":%d,"result":"%s","utc":"%s"}\n' $k $rc "$(grep -E '^test result' $O/core-run-$k.log | tail -1)" "$(date -u +%FT%TZ)" >> $O/core-reruns.jsonl
  done )
python3 - "$O" <<'EOF'
import json, re, sys
from pathlib import Path
O = Path(sys.argv[1]); log = (O / "core-run-1.log").read_text()
m = re.findall(r"test result: (\w+)\. (\d+) passed; (\d+) failed; (\d+) ignored", log)[-1]
rc = json.loads((O / "core-reruns.jsonl").read_text().splitlines()[0])["rc"]
row = {"schema": "ar.build.v1", "kind": "test", "suite": "cua-driver-core --lib", "ok": m[0] == "ok" and rc == 0,
       "passed": int(m[1]), "failed": int(m[2]), "ignored": int(m[3]), "rc": rc, "diagnostic_rerun": True}
(O / "core-row.json").write_text(json.dumps(row) + "\n")
EOF
for spec in "sleep20 1 ar-calib2-sleep20-9c1d9296b" "noop05 13 ar-calib2-noop05-6fceb666f"; do
  set -- $spec; NAME=$1; IDX=$2; LABEL=$3; E=$O/$NAME; mkdir -p $E
  SSEED=$((20261102 + 1000*IDX + 10 + 1)); CSEED=$((20261102 + 1000*IDX + 10 + 2))
  CAND=$L/bin/cua-driver-$LABEL
  REQ=$(awk -v n="$NAME" '$1==n{print $2}' $D/submit.log)
  { grep '"kind": "build"' $D/g1/$NAME.rows.jsonl; grep '"suite": "platform-linux --lib"' $D/g1/$NAME.rows.jsonl; cat $O/core-row.json; } > $E/g1.diag.rows.jsonl
  python3 $A/ar-eval g0 --repo $REPO --champion $CH --candidate ar/calib2/$NAME --itemcheck <mnt>/cargo-targets/ar-itemcheck/release/itemcheck --out $E/g0.inputs.json > $E/g0.json
  python3 $A/ar-eval prereg --request "$REQ" --eval-id ar-20261002-cal2diag-$NAME --champion-commit $CH \
    --candidate-commit "$(git -C $REPO rev-parse ar/calib2/$NAME)" --champion-bin $CHAMP --candidate-bin $CAND \
    --tau $TAU --harness-commit $HC --seed $CSEED --soak 300 --n01 "diagnostic" --out $E/prereg.json > /dev/null || exit 3
  python3 $A/runner/plan.py --eval-id ar-20261002-cal2diag-$NAME-scr --champion $CHAMP --candidate $CAND --pairs 24 --seed $SSEED --out $E/screen-plan.json > /dev/null
  python3 $A/runner/run_blocks.py --plan $E/screen-plan.json --out-dir $E/screen --wt $H --label ar-20261002-cal2diag-$NAME-scr > $E/screen-blocks.out 2>&1
  echo "rc=$?" >> $E/screen-blocks.out
  python3 $D/tools/screen.py --harness $A --prereg $E/prereg.json --rows $E/screen/raw/*.jsonl --build-rows $E/g1.diag.rows.jsonl \
    --g0 $E/g0.json --seed $SSEED --out $E/screen.json
done
echo DIAG_DONE > $O/done
