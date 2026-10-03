#!/usr/bin/env python3
"""R2-10 verifier mutation control (UNIT; standard library only; run under bin/hostless).

Clean shared clone of <repo> at <rev>; run the R2-10 packet verifier with --skip-git on the unmodified
README, then on a README where every "27.60" becomes "27.61" and every "0.98 [" becomes "0.97 [".
A discriminating verifier fails exactly the checks that cite those numbers. The clone lives under
$TMPDIR and is removed. Prints the verifier summary lines only.

usage: mutation_control.py <repo> <rev> [packet-dir]
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo, rev = sys.argv[1], sys.argv[2]
pkt = sys.argv[3] if len(sys.argv) > 3 else "docs/experiments/r2-10-composition-2026-10-02"
work = Path(tempfile.mkdtemp(prefix="pub02-mutation-"))
try:
    clone = work / "repo"
    subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", repo, str(clone)], check=True)
    subprocess.run(["git", "-C", str(clone), "checkout", "-q", "--detach", rev], check=True)
    here = clone / pkt
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"clone at {head}; packet {pkt}")
    readme = here / "README.md"
    original = readme.read_text()
    mutated = original.replace("27.60", "27.61").replace("0.98 [", "0.97 [")
    print(f"mutation: '27.60'->'27.61' x{original.count('27.60')}, '0.98 ['->'0.97 [' x{original.count('0.98 [')}")
    for label, text in (("unmutated", original), ("mutated", mutated)):
        readme.write_text(text)
        r = subprocess.run([sys.executable, "-B", "verify_artifacts.py", "--skip-git"], cwd=here,
                           capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        fails = [line for line in r.stdout.splitlines() if line.startswith("[FAIL]")]
        total = [line for line in r.stdout.splitlines() if line.endswith("checks passed")]
        print(f"{label}: rc={r.returncode} {total[-1] if total else 'no summary'}; FAIL lines: {len(fails)}")
        for line in fails:
            print(f"  {line[:200]}")
finally:
    shutil.rmtree(work, ignore_errors=True)
