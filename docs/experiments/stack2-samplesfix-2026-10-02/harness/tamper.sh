#!/usr/bin/env bash
# PREREG C3 tamper tests: each edit, on a fresh scratch copy of the SAMPLES packet, must make
# verify_artifacts.py print RESULT FAIL.
#   $HOSTLESS harness/tamper.sh <samples_packet_dir> <scratch_dir>
set -u
SRC="$1"; T="$2/tamper"; rm -rf "$T"; mkdir -p "$T"
export TMPDIR="$2" PYTHONDONTWRITEBYTECODE=1
run() { # name, python edit snippet
  local d="$T/$1"; cp -r "$SRC" "$d"
  (cd "$d" && python3 -c "$2") || { echo "TAMPER $1 edit failed"; return; }
  out=$(cd "$d" && python3 verify_artifacts.py 2>&1); rc=$?
  echo "TAMPER $1 rc=$rc $(echo "$out" | tail -1)"; echo "$out" | grep '^FAIL' | sed 's/^/    /'
}
run a_verdict 'import json,pathlib
p=pathlib.Path("raw/collect/verdicts.jsonl"); L=p.read_text().splitlines(); d=json.loads(L[0]); d["verified_success"]=not d["verified_success"]; L[0]=json.dumps(d); p.write_text("\n".join(L)+"\n")'
run b_table_cell 'import pathlib
p=pathlib.Path("README.md"); s=p.read_text(); old="| julia_1 (CPU) | 0.2466 |"; assert s.count(old)==1; p.write_text(s.replace(old,"| julia_1 (CPU) | 0.2467 |"))'
run c_agent_log 'import pathlib,re
p=pathlib.Path("raw/runs/S-t024-cua_button_present-02/agent.log"); s=p.read_text(); n=len(re.findall(r"Tool tool_call returned error \([^)]*\): .*", s)); assert n==1
p.write_text(re.sub(r"Tool tool_call returned error \([^)]*\): .*", "tool tool_call completed (0.01s, 10 chars)", s))'
run d_manifest_count 'import json,pathlib
p=pathlib.Path("dataset/MANIFEST.json"); d=json.loads(p.read_text()); d["counts"]["observer_rows"]-=1; p.write_text(json.dumps(d,indent=2,sort_keys=True)+"\n")'
rm -rf "$T"
