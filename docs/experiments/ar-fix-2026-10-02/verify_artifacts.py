#!/usr/bin/env python3
"""Re-check the fix-round packet from its files alone (run under hostless from anywhere).

Uses the standard library plus the evaluator's pure functions (harness/ar on this branch):
  1. MANIFEST.sha256 covers every packet file and matches;
  2. the pre-registration hash matches and was taken before the first A/A block started;
  3. the A/A checks (raw/checks.json) recompute from raw/aa/*.jsonl.gz: T_act CI includes 0, the
     whole-task guardrail, G2 (with the live candidate-only soak session), G3, G4, no false keep;
  4. the R3 replay diagnostic (raw/replay.json) recomputes from the calibration packet's raw rows;
  5. no host paths, host names or credentials in any packet file.
Prints one line per check and exits non-zero if any fails.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[2] / "harness" / "ar"
CALIB = HERE.parent / "ar-calibration-2026-10-02" / "raw"
sys.path.insert(0, str(HARNESS))
from areval import aa, gates  # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{(': ' + detail) if detail else ''}")
    if not ok:
        fails.append(name)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rows_of(paths) -> list[dict]:
    return [json.loads(x) for p in paths for x in gzip.decompress(p.read_bytes()).decode().splitlines() if x.strip()]


# 1. manifest
man = {}
for line in (HERE / "MANIFEST.sha256").read_text().splitlines():
    digest, rel = line.split(maxsplit=1)
    man[rel] = digest
files = sorted(str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and p.name != "MANIFEST.sha256"
               and "__pycache__" not in p.parts)
check("manifest covers every file", sorted(man) == files, f"{len(files)} files")
check("manifest hashes match", all(sha(HERE / r) == d for r, d in man.items() if (HERE / r).exists()))

# 2. pre-registration
pre_line = (HERE / "raw/FIX-PREREG.sha256").read_text().split()
check("prereg hash", pre_line[0] == sha(HERE / "raw/FIX-PREREG.json"))
blocks = [json.loads(x) for x in (HERE / "raw/aa/blocks.jsonl").read_text().splitlines() if x.strip()]
check("prereg hashed before the first A/A block", pre_line[-1] < min(b["started_utc"] for b in blocks),
      f"{pre_line[-1]} < {min(b['started_utc'] for b in blocks)}")
check("every A/A block rc 0", all(b["rc"] == 0 for b in blocks), f"{len(blocks)} blocks")

# 3. A/A checks
rec = json.loads((HERE / "raw/checks.json").read_text())
rows = rows_of(sorted((HERE / "raw/aa").glob("s*.jsonl.gz")))
s = aa.summarize(rows)
t, w = s["T_act"], s["whole_task_T"]
check("T_act Delta_AA recomputes", abs(t["delta_aa_ln"] - rec["T_act"]["delta_aa_ln"]) < 1e-12)
check("PRIMARY: T_act CI95 includes 0", t["ci_includes_zero"] and rec["primary_T_act_ci_includes_zero"],
      f"{t['delta_aa_ln']:+.4f} [{t['ci95_ln'][0]:+.4f}, {t['ci95_ln'][1]:+.4f}]")
check("whole-task guardrail on the A/A", w["delta_aa_ln"] <= math.log1p(0.0311),
      f"{w['delta_aa_ln']:+.4f} <= {math.log1p(0.0311):.4f}")
g2 = gates.g2(rows, {"invariants": {"expected_route": "accessibility", "expected_path": None}})
check("G2 passes incl. the candidate-only soak session", g2["pass"] and rec["G2"]["pass"], ";".join(g2["reasons"][:2]))
starts = {r["session"]: r for r in rows if r.get("schema") == "ar.session.v1" and r.get("event") == "start"}
soak = {r["session"] for r in gates.trials(rows, kind="soak")}
paired = {r["session"] for r in gates.trials(rows, kind="task") if r.get("pair_id")}
dbus = {k: v["session_binds"]["dbus"] for k, v in starts.items()}
check("live F1 is not vacuous (soak session D-Bus name is its own)",
      bool(soak) and all(dbus[x] not in {dbus[y] for y in paired} for x in soak)
      and all(any(dbus[x] in r["footprint"]["home_files"] for r in gates.trials(rows, kind="soak")) for x in soak))
check("old evaluator (2615af74f) G2 fails these rows (recorded)", not rec["old_evaluator_G2"]["pass"],
      ";".join(rec["old_evaluator_G2"]["reasons"][:1]))
check("G3, G4 pass; A/A not kept", s["gates_on_aa"]["G3"]["pass"] and s["gates_on_aa"]["G4"]["pass"]
      and not s["gates_on_aa"]["G5_false_keep_check"]["pass"])

# 4. replay diagnostic
rep = json.loads((HERE / "raw/replay.json").read_text())
out = HERE / ".replay-recheck.json"
subprocess.run([sys.executable, str(HERE / "tools/replay_r3.py"), "--run-dir", str(CALIB), "--harness", str(HARNESS),
                "--out", str(out)], check=True, capture_output=True)
again = json.loads(out.read_text())
out.unlink()
same = [(a["verdict"], a["failed_gate"], a["p_value"]) for a in again["evaluations"]] == \
       [(a["verdict"], a["failed_gate"], a["p_value"]) for a in rep["evaluations"]]
check("R3 replay recomputes from the calibration packet", same, f"{again['keeps']}/10 KEEP")

# 5. leaks
host = Path("/etc/hostname").read_text().strip() if Path("/etc/hostname").exists() else ""
pat = re.compile(r"/mnt/|/home/(?!trial\b)[a-z]|ghp_|sk-ant-|github_pat_" + (f"|{re.escape(host)}" if host else ""))
bad = []
for rel in files:
    p = HERE / rel
    data = gzip.decompress(p.read_bytes()).decode(errors="replace") if p.suffix == ".gz" else p.read_text(errors="replace")
    if rel != "verify_artifacts.py" and pat.search(data):
        bad.append(rel)
check("no host paths, host name or credentials", not bad, ",".join(bad[:3]))

print(f"{'PASS' if not fails else 'FAIL'}: {len(fails)} failing")
sys.exit(1 if fails else 0)
