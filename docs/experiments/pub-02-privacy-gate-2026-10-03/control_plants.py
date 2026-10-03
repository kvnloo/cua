#!/usr/bin/env python3
"""Template privacy-scan controls (UNIT; standard library only; run under bin/hostless).

For each control, a fresh throwaway git repository under $TMPDIR gets a copy of docs/experiments/_template
at <rev> (README, .gitignore, verify_helper.py, test file) as a packet, a clean raw/trials.jsonl, one
plant, one commit; then
`python3 verify_helper.py <packet> --privacy` runs. The names file holds only a non-private dummy name
built at run time. Nothing here is committed to any branch.

  hex      the dummy hex-encoded in a text file            expected: caught (rc 1)
  base64   the dummy base64-encoded in a JSON file         expected: caught
  gzip     the dummy plain inside a raw/ gzip member       expected: caught
  abspath  a home-directory path in a raw/ text file       expected: caught
  enclist  two quoted base64 literals of name-like tokens  expected: caught (no names file entry needed)
  clean    the template copy with no plant                 expected: pass (rc 0)

usage: control_plants.py <repo> <rev>
"""
import base64
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

repo, rev = sys.argv[1], sys.argv[2]
DUMMY = "zz-" + "planted-name"
ABS = "/" + "home/example-user/work/run"
ENC = [base64.b64encode(n.encode()).decode() for n in ("alpha-node-01", "beta-node-02")]
PLANTS = {
    "hex": ("notes.txt", f"id {DUMMY.encode().hex()} end\n".encode()),
    "base64": ("cfg.json", (json.dumps({"k": base64.b64encode(DUMMY.encode()).decode()}) + "\n").encode()),
    "gzip": ("raw/log.txt.gz", gzip.compress(f"session {DUMMY} ok\n".encode(), mtime=0)),
    "abspath": ("raw/run.txt", f"cwd={ABS}\n".encode()),
    "enclist": ("check.py", f"_N = [{ENC[0]!r}, {ENC[1]!r}]\n".encode()),
    "clean": (None, b""),
}
EXPECT = {k: (0 if k == "clean" else 1) for k in PLANTS}
files = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "--name-only", rev, "docs/experiments/_template/"],
                       capture_output=True, text=True, check=True).stdout.split()
work = Path(tempfile.mkdtemp(prefix="pub02-plants-"))
env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.invalid", CUA_PRIVACY_NAMES_FILE=str(work / "names.txt"),
           PYTHONDONTWRITEBYTECODE="1")
(work / "names.txt").write_text(DUMMY + "\n")
print(f"template and helper from {subprocess.run(['git', '-C', repo, 'rev-parse', rev], capture_output=True, text=True).stdout.strip()}")
caught, rcs = {}, {}
try:
    for name, (path, data) in PLANTS.items():
        r = work / name
        pkt = r / "docs" / "experiments" / "example"
        (pkt / "raw").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(r)], check=True, env=env)
        for f in files:
            blob = subprocess.run(["git", "-C", repo, "show", f"{rev}:{f}"], capture_output=True, check=True).stdout
            (pkt / Path(f).name).write_bytes(blob)
        (pkt / "raw" / "trials.jsonl").write_text('{"trial": 1}\n')  # a clean raw/ file for the cited raw/
        if path:
            (pkt / path).write_bytes(data)
        subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "control"], check=True, env=env)
        p = subprocess.run([sys.executable, "-B", "verify_helper.py", ".", "--privacy"], cwd=pkt,
                           capture_output=True, text=True, env=env)
        ok = p.returncode == EXPECT[name]
        rcs[name] = p.returncode
        hit = [line for line in p.stdout.splitlines() if line.startswith("FAIL privacy")]
        caught[name] = name != "clean" and p.returncode == 1 and any(path in line for line in hit)
        print(f"{name}: plant {path or '-'}; rc={p.returncode} expected {EXPECT[name]} -> {'as expected' if ok else 'NOT as expected'}")
        for line in p.stdout.splitlines():
            if line.startswith(("FAIL", "PASS")):
                print(f"  {line[:200]}")
finally:
    shutil.rmtree(work, ignore_errors=True)
print(f"dummy name caught: {sum(caught[k] for k in ('hex', 'base64', 'gzip'))}/3; abs-path plant caught: {int(caught['abspath'])}/1; encoded-list plant caught: {int(caught['enclist'])}/1; clean template passes: {'yes' if rcs['clean'] == 0 else 'no'}")
