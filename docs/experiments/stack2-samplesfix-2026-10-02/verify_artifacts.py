#!/usr/bin/env python3
"""Re-check of the stack2-samplesfix-2026-10-02 packet (stdlib + git, no models, no network).

  python3 verify_artifacts.py             -> RESULT PASS | RESULT FAIL (exit 1)
  python3 verify_artifacts.py --tamper    -> also re-runs the 4 tamper copies (needs bash; slower)

  1  PREREG.json was committed before every commit that changed the SAMPLES packet after base 4c1a4a95e
  2  raw/samples-README-at-4c1a4a95.md is byte-identical to the SAMPLES README at the base commit
  3  the SAMPLES packet's verify_artifacts.py prints RESULT PASS (checks 1-14, incl. CUA attribution,
     generated tables, summary, MANIFEST, unit log)
  4  C6: every number of the original SAMPLES results tables is still in the corrected tables
  5  summary.json key numbers == the SAMPLES packet's committed cua-bridge tally; the SAMPLES README
     carries the E2 notice and the withdrawal; provenance carries E1-E6
  6  C3 tamper receipt: 4 tamper copies, each RESULT FAIL (re-run with --tamper)
  7  raw/smoke-positive-control.txt sums to the figure quoted in both READMEs
  8  no absolute local paths, private markers or secret-looking strings in this packet
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "stack-samples-2026-10-02"
BASE = "4c1a4a95e"
FAIL: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], check=True, capture_output=True, text=True).stdout


def main() -> None:
    # 1 PREREG before the repair commits
    try:
        prereg = git("log", "--diff-filter=A", "--format=%H", "--", "PREREG.json").split()[-1]
        repair = git("rev-list", f"{BASE}..HEAD", "--", str(SAMPLES)).split()
        ok = bool(repair) and all(c != prereg and subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", prereg, c]).returncode == 0
                                  for c in repair)
        check(ok, f"1 PREREG {prereg[:9]} precedes all {len(repair)} commit(s) that changed the SAMPLES packet")
        old = git("show", f"{BASE}:docs/experiments/stack-samples-2026-10-02/README.md")
        check((HERE / "raw" / "samples-README-at-4c1a4a95.md").read_text(encoding="utf-8") == old,
              "2 old README copy is byte-identical to the base commit's README")
    except (subprocess.CalledProcessError, FileNotFoundError, IndexError) as e:
        check(False, f"1/2 git history unavailable ({e.__class__.__name__}); run inside the repository")

    # 3 SAMPLES packet verifier
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, str(SAMPLES / "verify_artifacts.py")], capture_output=True, text=True, env=env)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    check(r.returncode == 0 and last == "RESULT PASS",
          f"3 SAMPLES verify_artifacts.py: {last} ({sum(l.startswith('ok ') for l in r.stdout.splitlines())} ok lines)")

    # 4 numbers kept
    sys.path.insert(0, str(HERE / "harness"))
    import numbers_kept  # noqa: E402
    res = numbers_kept.compare((HERE / "raw" / "samples-README-at-4c1a4a95.md").read_text(encoding="utf-8"),
                               (SAMPLES / "README.md").read_text(encoding="utf-8"))
    check(res == json.loads((HERE / "raw" / "numbers-kept.json").read_text()) and res["all_kept"],
          "4 every number of the original workload/api/turn tables is in the corrected tables (numbers-kept.json reproduces)")

    # 5 key numbers, notice, errata
    tally = json.loads((SAMPLES / "raw" / "analysis" / "cua-bridge-tally.json").read_text())["totals"]
    summ = json.loads((HERE / "summary.json").read_text())
    check(summ["cua_bridge"] == tally, "5 summary.json cua_bridge == committed tally totals")
    sr = (SAMPLES / "README.md").read_text(encoding="utf-8")
    notice = sr.split("> **Corrected by SAMPLESFIX", 1)[1].split("\n\n", 1)[0] if "> **Corrected by SAMPLESFIX" in sr else ""
    check(f"All {tally['tool_errors']} tool calls" in notice and "**withdrawn**" in notice,
          f"5 SAMPLES README opens with the E2 notice ({tally['tool_errors']} refused tool calls, bypass withdrawn)")
    errata = {e["id"]: e for e in json.loads((SAMPLES / "provenance.json").read_text())["errata"]}
    check(sorted(errata) == ["E1", "E2", "E3", "E4", "E5", "E6"] and all(errata[k].get("by") == "SAMPLESFIX" for k in ("E2", "E3", "E4", "E5", "E6"))
          and "invented" in errata["E1"]["what"], "5 SAMPLES provenance carries E1 (plain wording) and E2-E6")
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for k in ("tool_errors", "api_calls_agent_log"):
        check(f"{tally[k]}" in readme, f"5 lane README quotes {k} = {tally[k]}")

    # 6 tamper
    if "--tamper" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run(["bash", str(HERE / "harness" / "tamper.sh"), str(SAMPLES), tmp], capture_output=True, text=True).stdout
    else:
        out = (HERE / "raw" / "tamper.log").read_text()
    lines = [l for l in out.splitlines() if l.startswith("TAMPER ")]
    check(len(lines) == 4 and all(l.endswith("RESULT FAIL") for l in lines),
          f"6 tamper: {len(lines)} copies, all RESULT FAIL ({'re-run' if '--tamper' in sys.argv else 'receipt raw/tamper.log'})")

    # 7 smoke positive control
    pc = [l.split() for l in (HERE / "raw" / "smoke-positive-control.txt").read_text().splitlines() if l and not l.startswith("#")]
    total = sum(int(x[0]) for x in pc)
    check(total == summ["smoke_positive_control_dispatch_lines"] and f"{total}" in readme and f"{total}" in sr,
          f"7 SMOKE positive control: {total} 'tool computer_use completed' lines in {len(pc)} agent.logs")

    # 8 hygiene
    abs_path = re.compile(r"(?<![\w$}.~-])/(mnt|home|workspace|run/user|srv|opt)/[A-Za-z0-9]")
    markers = [m for m in os.environ.get("STACK_PRIVATE_MARKERS", "").split(":") if m]
    secret = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
    hits = [str(p.relative_to(HERE)) for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts
            and (abs_path.search(t := p.read_text(errors="replace")) or secret.search(t) or any(m in t for m in markers))]
    check(not hits, f"8 no absolute local paths / private markers ({len(markers)}) / secret-looking strings ({hits[:5]})")

    print("RESULT", "PASS" if not FAIL else "FAIL")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
