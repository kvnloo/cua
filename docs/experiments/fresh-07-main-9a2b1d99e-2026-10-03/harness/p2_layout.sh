#!/usr/bin/env bash
# FRESH-07: arrange the Phase 2 run directories into the layouts the ORIGINAL packagers/analyzers read,
# then package them into the packet with machine paths scrubbed (run through hostless).
#   p2_layout.sh <runs-root> <stage-dir> <packet-dir>
# Scrub pairs come from FRESH07_REDACT ('old=new;...'), never from this file.
set -uo pipefail
RUNS="$1"; ST="$2"; PK="$3"
PY=python3
mkdir -p "$ST"
# ---- R2-10R: orig/r2-10r/harness/package_raw.py layout: <runs>/m/{scripted,native-<blk>}, <runs>/p0/d-*
R="$ST/r210r-runs"; rm -rf "$R"; mkdir -p "$R/m" "$R/p0"
[ -d "$RUNS/r210r/scripted" ] && ln -s "$RUNS/r210r/scripted" "$R/m/scripted"
for blk in nm1 nm2 nd1; do [ -d "$RUNS/r210r/native-$blk" ] && ln -s "$RUNS/r210r/native-$blk" "$R/m/native-$blk"; done
for lab in R C; do
  T="$RUNS/r210r/smoke/tools-$lab"
  if [ -d "$T" ]; then
    mkdir -p "$R/p0/d-tools-$lab"
    cp "$T/tools-$lab-toolslist.json" "$R/p0/d-tools-$lab/D$lab-toolslist.json"
    cp "$T/tools-$lab-toolslist-0.json" "$R/p0/d-tools-$lab/D$lab-toolslist-0.json"
  fi
  [ -d "$RUNS/r210r/smoke/smoke-$lab" ] && ln -s "$RUNS/r210r/smoke/smoke-$lab" "$R/p0/d-smoke-$lab"
  [ -d "$RUNS/r210r/native-ns$lab" ] && ln -s "$RUNS/r210r/native-ns$lab" "$R/p0/d-native-$lab"
done
: > "$ST/empty-ledger.jsonl"
scrubs=()
IFS=';' read -ra pairs <<< "${FRESH07_REDACT:-}"
for p in "${pairs[@]}"; do [ -n "$p" ] && scrubs+=(--scrub "$p"); done
scrubs+=(--scrub "$(hostname)=<host>")
rm -rf "$PK/p2/r2-10r/raw"
"$PY" "$PK/orig/r2-10r/harness/package_raw.py" --runs "$R" --raw "$PK/p2/r2-10r/raw" "${scrubs[@]}" \
  --lane-ledger "$ST/empty-ledger.jsonl" --global-ledger "$ST/empty-ledger.jsonl" > "$ST/r210r-package-report.json"
# ---- N-04: orig/n-04/analyze_n04.py reads <raw>/runs/<label>/trials.jsonl*
mkdir -p "$PK/p2/n-04/raw/runs"
for d in "$RUNS"/n04/n04-*/; do
  l=$(basename "$d"); [ -f "$d/trials.jsonl" ] || continue
  "$PY" "$PK/package_raw.py" "$d/trials.jsonl" "$ST/n04-tmp/$l/trials.jsonl" >/dev/null
  mkdir -p "$PK/p2/n-04/raw/runs/$l"; gzip -nc "$ST/n04-tmp/$l/trials.jsonl" > "$PK/p2/n-04/raw/runs/$l/trials.jsonl.gz"
  [ -f "$d/DONE" ] && : > "$PK/p2/n-04/raw/runs/$l/DONE"
done
for f in "$RUNS"/n04/load-gate.jsonl; do [ -f "$f" ] && "$PY" "$PK/package_raw.py" "$f" "$PK/p2/n-04/raw/load-gate.jsonl"; done
# ---- chunk session logs and the lane's shared-lock receipts
for lane in r210r n04; do
  [ -d "$RUNS/$lane/chunks" ] && "$PY" "$PK/package_raw.py" "$RUNS/$lane/chunks" "$PK/p2/chunks/$lane"
  [ -f "$RUNS/$lane/lock-ledger-shared.jsonl" ] && "$PY" "$PK/package_raw.py" "$RUNS/$lane/lock-ledger-shared.jsonl" "$PK/p2/locks/$lane-shared.jsonl"
done
[ -f "$RUNS/r210r/scripted/load-gate.jsonl" ] && "$PY" "$PK/package_raw.py" "$RUNS/r210r/scripted/load-gate.jsonl" "$PK/p2/r2-10r/load-gate.jsonl"
exit 0
