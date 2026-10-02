#!/usr/bin/env python3
"""verify_artifacts.py: offline check of the MULTISEAT packet. Run from anywhere: python3 verify_artifacts.py

  1. MANIFEST.sha256 matches every packet file (tamper check).
  2. Re-grades raw/measured with harness/grade.py and requires byte-equal JSON to grade.json.
  3. Re-summarises with harness/summarize.py and requires equality with summary.json.
  4. Denominators match PREREG.json (64 main + 10 look-alike agent runs, 3 cross-wire reps, 3 + 2 seat reps);
     every launched agent run is graded.
  5. PREREG.json is byte-identical to the preregistration commit, and that commit is older than the first
     measured round (git, when the packet is inside a checkout; otherwise provenance.json is reported).
  6. No local absolute paths, host name or secret-looking strings in the packet.
Prints RESULT PASS / RESULT FAIL.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
fails, notes = [], []


def check(ok, msg):
    (notes if ok else fails).append(("ok   " if ok else "FAIL ") + msg)


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# 1 manifest
man = os.path.join(HERE, "MANIFEST.sha256")
listed = {}
for line in open(man):
    h, rel = line.rstrip("\n").split("  ", 1)
    listed[rel] = h
bad = [r for r, h in listed.items() if not os.path.exists(os.path.join(HERE, r)) or sha(os.path.join(HERE, r)) != h]
present = set()
for root, _d, files in os.walk(HERE):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), HERE)
        if rel not in ("MANIFEST.sha256",) and "__pycache__" not in rel:
            present.add(rel)
check(not bad, f"manifest: {len(listed)} files, mismatched/missing {bad[:5]}")
check(present == set(listed), f"manifest covers every file (unlisted {sorted(present - set(listed))[:5]})")

# 2 regrade
with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "grade.json")
    args = [sys.executable, os.path.join(HERE, "harness/grade.py"), os.path.join(HERE, "raw/measured"), out,
            "--server-log", os.path.join(HERE, "raw/measured/server-requests.log")]
    r = subprocess.run(args, capture_output=True, text=True)
    check(r.returncode == 0, f"grade.py ran (rc {r.returncode}) {r.stderr[-300:]}")
    if r.returncode == 0:
        check(json.load(open(out)) == json.load(open(os.path.join(HERE, "grade.json"))), "regrade == grade.json")
        sout = os.path.join(td, "summary.json")
        r2 = subprocess.run([sys.executable, os.path.join(HERE, "harness/summarize.py"), out, sout],
                            capture_output=True, text=True)
        check(r2.returncode == 0 and json.load(open(sout)) == json.load(open(os.path.join(HERE, "summary.json"))),
              "re-summary == summary.json")

# 4 denominators
g = json.load(open(os.path.join(HERE, "grade.json")))
main_runs = sum(len(r["agents"]) for r in g["main_rounds"])
look_runs = sum(len(r["agents"]) for r in g["lookalike_rounds"])
check(len(g["main_rounds"]) == 16 and main_runs == 64, f"main: {len(g['main_rounds'])} rounds, {main_runs} agent runs (prereg 16 / 64)")
check(len(g["lookalike_rounds"]) == 5 and look_runs == 10, f"look-alike: {len(g['lookalike_rounds'])} rounds, {look_runs} agent runs (prereg 5 / 10)")
check(len(g["crosswire"]["reps"]) == 3, f"cross-wire reps {len(g['crosswire']['reps'])} (prereg 3)")
check(len(g["seat_lookalike"]) == 3 and len(g["seat_driver"]) == 2,
      f"seat reps {len(g['seat_lookalike'])} + {len(g['seat_driver'])} (prereg 3 + 2)")
for r in g["main_rounds"] + g["lookalike_rounds"]:
    for a in r["agents"]:
        if not a.get("launched"):
            check(False, f"agent not graded: {r['round']} {a['aid']}")

# 5 prereg ordering
prov = json.load(open(os.path.join(HERE, "provenance.json")))
pc = prov["prereg_commit"]
rounds_t0 = []
for kind in ("main", "lookalike"):
    d = os.path.join(HERE, "raw/measured", kind)
    for rd in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        p = os.path.join(d, rd, "round.json")
        if os.path.exists(p):
            rounds_t0.append(json.load(open(p))["t0"])
first_t0 = min(rounds_t0) if rounds_t0 else None
rel = os.path.relpath(os.path.join(HERE, "PREREG.json"), subprocess.run(
    ["git", "-C", HERE, "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or HERE)
gshow = subprocess.run(["git", "-C", HERE, "show", f"{pc}:{rel}"], capture_output=True)
if gshow.returncode == 0:
    check(gshow.stdout == open(os.path.join(HERE, "PREREG.json"), "rb").read(), f"PREREG.json identical to prereg commit {pc[:12]}")
    ct = subprocess.run(["git", "-C", HERE, "show", "-s", "--format=%ct", pc], capture_output=True, text=True).stdout.strip()
    check(first_t0 is not None and int(ct) < first_t0, f"prereg commit time {ct} < first measured round t0 {first_t0}")
else:
    notes.append(f"note prereg commit {pc[:12]} not in this checkout; provenance says committed {prov.get('prereg_commit_time')}")
    check(first_t0 is not None and prov.get("prereg_commit_epoch", 1e20) < first_t0, "provenance prereg epoch < first measured t0")

# 6 scan
pat = re.compile(r"(/mnt/[A-Za-z0-9_-]+/|/home/[a-z][a-z0-9_-]*/|/workspace/[a-z]|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})")
HOST_SHA = prov.get("host_name_sha256")  # the host name itself is never written into the packet
hits = []
for rel_ in sorted(present):
    p = os.path.join(HERE, rel_)
    if p.endswith(".png"):
        continue
    try:
        txt = open(p, encoding="utf-8").read()
    except UnicodeDecodeError:
        continue
    if rel_ == "verify_artifacts.py":
        continue
    for m in pat.finditer(txt):
        hits.append(f"{rel_}: {m.group(0)}")
    if HOST_SHA:
        for tok in set(re.findall(r"[A-Za-z0-9-]{3,32}", txt)):
            if hashlib.sha256(tok.lower().encode()).hexdigest() == HOST_SHA:
                hits.append(f"{rel_}: <host name>")
check(not hits, f"path/host/secret scan: {len(hits)} hits {hits[:5]}")

for n in notes + fails:
    print(n)
print("RESULT", "FAIL" if fails else "PASS")
sys.exit(1 if fails else 0)
