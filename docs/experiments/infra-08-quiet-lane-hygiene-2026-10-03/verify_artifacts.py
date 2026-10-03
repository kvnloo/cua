#!/usr/bin/env python3
"""INFRA-08 packet verifier.

  verify_artifacts.py                       static checks only (no process is started except `diff`)
  verify_artifacts.py --rerun --tmp DIR     also re-runs tests/test_quiet_lane.py for v1 and v2 into DIR
  verify_artifacts.py --installed-bin BIN --live-lockdir LOCKDIR
                                            also checks the install record against BIN (sha256 of the
                                            installed files) and renders the templates with LOCKDIR to
                                            prove the installed files are exactly the rendered templates

Run under bin/hostless (it refuses otherwise). Exit 0 iff every check passes.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["scripts/quiet-timed", "scripts/quiet-shared", "scripts/quiet-holders", "scripts/v1/quiet-timed"]
PLACEHOLDER = "@QUIET_LANE_DEFAULT_LOCKDIR@"
FORBIDDEN = ["/" + d + "/" for d in ("mnt", "home", "tmp", "root")]  # built so the packet itself has no such literal
fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rows(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--tmp")
    ap.add_argument("--installed-bin")
    ap.add_argument("--live-lockdir")
    a = ap.parse_args()
    if os.environ.get("CUA_HOSTLESS") != "1":
        sys.exit("refusing to run outside bin/hostless (CUA_HOSTLESS=1 not set)")
    summary = json.load(open(os.path.join(HERE, "summary.json")))
    prov = json.load(open(os.path.join(HERE, "provenance.json")))
    json.load(open(os.path.join(HERE, "PREREG.json")))

    # 1. templates: placeholder present, no local paths, hashes match provenance
    for s in SCRIPTS:
        text = open(os.path.join(HERE, s)).read()
        check(text.count(PLACEHOLDER) == 1, f"{s}: exactly one {PLACEHOLDER}")
        check(not any(p in text for p in FORBIDDEN), f"{s}: no absolute local path")
        check(prov["templates_sha256"][s] == sha(os.path.join(HERE, s)), f"{s}: sha256 matches provenance")
        if s != "scripts/v1/quiet-timed":
            check(any(l.startswith("# USAGE") for l in text.splitlines()[:6]), f"{s}: USAGE note at the head")
    for s in ["tests/test_quiet_lane.py", "render.sh"]:
        check(prov["templates_sha256"][s] == sha(os.path.join(HERE, s)), f"{s}: sha256 matches provenance")

    # 2. the committed v1-vs-v2 diff is exactly the diff of the committed templates
    d = subprocess.run(["diff", "-u", "--label", "scripts/v1/quiet-timed", "--label", "scripts/quiet-timed",
                        "scripts/v1/quiet-timed", "scripts/quiet-timed"], cwd=HERE, capture_output=True, text=True)
    check(d.stdout == open(os.path.join(HERE, "v1-vs-v2.diff")).read(), "v1-vs-v2.diff regenerates byte-identical")

    # 3. every raw run is counted in the summary; final runs all match PREREG
    for run in summary["runs"]:
        for impl, s in run["impls"].items():
            r = rows(os.path.join(HERE, "raw", run["run"], f"{impl}.jsonl"))
            m = sum(1 for x in r if x["matches_expectation"])
            check(len(r) == s["rows"] and m == s["match"], f"{run['run']} {impl}: {m} of {len(r)} rows match "
                  f"(summary {s['match']} of {s['rows']})")
            check(all(x.get("evidence_class") == "UNIT" for x in r), f"{run['run']} {impl}: every row evidence_class UNIT")
            if run["counts_for_result"]:
                check(m == len(r), f"{run['run']} {impl}: all rows match PREREG")
    r1 = [x for x in rows(os.path.join(HERE, "raw/run1/v1.jsonl")) if x["test"] == "T3"]
    check(len(r1) == 1 and r1[0]["queued_flock_waiters"] == [] and r1[0]["rc"] == 127,
          "run1 v1 T3 is the documented invalid row (no waiter queued, rc 127), excluded from the result")
    final = [r for r in summary["runs"] if r["counts_for_result"]]
    check([r["run"] for r in final] == ["run8", "run9", "run10"], "result runs are run8-run10")
    for r in final:
        check(r["scripts_sha256_quiet_timed"] == prov["templates_sha256"]["scripts/quiet-timed"],
              f"{r['run']}: ran on the final quiet-timed template")
    # red-before / green-after per test (run10), and the v2pre orphan defect (run7 + stress)
    v1 = {(x["test"], x["case"]): x["observed"] for x in rows(os.path.join(HERE, "raw/run10/v1.jsonl"))}
    v2 = {(x["test"], x["case"]): x["observed"] for x in rows(os.path.join(HERE, "raw/run10/v2.jsonl"))}
    check(v1[("T1", "quiet-timed daemon fd leak")] == "RED" and v2[("T1", "quiet-timed daemon fd leak")] == "GREEN",
          "T1 red on v1, green on v2")
    check(v1[("T3", "waiter reap on TERM")] == "RED" and v2[("T3", "waiter reap on TERM")] == "GREEN",
          "T3 red on v1, green on v2")
    check(v1[("T5", "starvation alarm")] == "RED" and v2[("T5", "starvation alarm")] == "GREEN",
          "T5 red on v1, green on v2")
    check(all(v == "GREEN" for v in v2.values()), "every v2 row GREEN in run10")
    pre = {x["test"]: x for x in rows(os.path.join(HERE, "raw/run7/v2pre.jsonl"))}
    check(pre["T7"]["observed"] == "RED" and v2[("T7", "quiet-timed no leftover on uncontended run")] == "GREEN",
          "T7 red on v2pre (first installed v2), green on final v2")
    check(sha(os.path.join(HERE, "scripts/history/quiet-timed.v2pre"))
          == prov["quiet_timed_template_history_sha256"]["runs 4-5 = v2pre, installed as install_1 (orphan defect)"],
          "scripts/history/quiet-timed.v2pre is the install_1 template")
    st = summary["stress"]
    for impl in ("v2", "v2pre"):
        for x in rows(os.path.join(HERE, f"raw/stress/{impl}-t7x300.jsonl")):
            tool = "quiet-timed" if x["test"] == "T7" else "quiet-shared"
            s = st[impl][tool]
            check(x["runs"] == s["runs"] and x["hung_pipes"] == s["hung"] and len(x["leftover_processes"]) == s["leftover"],
                  f"stress {impl} {tool}: {x['hung_pipes']} hung / {len(x['leftover_processes'])} leftover of {x['runs']} = summary")

    # 4. install record (sha256 only) is self-consistent
    inst = summary["install"]
    check(inst["v1_backup_sha256"] == inst["before"]["quiet-timed"] == inst["install_1"]["before"]["quiet-timed"],
          "backup sha256 = pre-install quiet-timed sha256")
    check(inst["install_2"]["before"]["quiet-timed"] == inst["install_1"]["after"]["quiet-timed"],
          "install_2 replaced exactly the install_1 quiet-timed")
    check(inst["after"] == inst["install_2"]["after"], "current install record = install_2")
    for name in ("quiet-timed", "quiet-shared", "quiet-holders"):
        check(len(inst["after"][name]) == 64, f"install record has an after-sha256 for {name}")
    if a.installed_bin:
        for name in ("quiet-timed", "quiet-shared", "quiet-holders"):
            check(sha(os.path.join(a.installed_bin, name)) == inst["after"][name], f"installed {name} sha256 matches record")
        check(sha(os.path.join(a.installed_bin, "quiet-timed.v1")) == inst["v1_backup_sha256"], "installed backup sha256 matches record")
    if a.live_lockdir:
        if not a.tmp:
            sys.exit("--live-lockdir needs --tmp (scratch dir for the render)")
        out = os.path.join(a.tmp, "render")
        subprocess.run([os.path.join(HERE, "render.sh"), a.live_lockdir, out], check=True)
        for name in ("quiet-timed", "quiet-shared", "quiet-holders"):
            check(sha(os.path.join(out, name)) == inst["after"][name], f"rendered {name} == installed sha256")
        check(sha(os.path.join(out, "v1/quiet-timed")) == inst["v1_backup_sha256"], "rendered v1 template == v1 backup sha256")
        pre_text = open(os.path.join(HERE, "scripts/history/quiet-timed.v2pre")).read().replace(PLACEHOLDER, a.live_lockdir)
        check(hashlib.sha256(pre_text.encode()).hexdigest() == inst["install_1"]["after"]["quiet-timed"],
              "rendered v2pre template == install_1 quiet-timed sha256")

    # 5. optional re-run
    if a.rerun:
        if not a.tmp:
            sys.exit("--rerun needs --tmp")
        for impl in ("v1", "v2"):
            out = os.path.join(a.tmp, f"rerun-{impl}.jsonl")
            p = subprocess.run([sys.executable, os.path.join(HERE, "tests/test_quiet_lane.py"), "--impl", impl,
                                "--tmp", os.path.join(a.tmp, "rerun"), "--out", out])
            r = rows(out)
            check(p.returncode == 0 and all(x["matches_expectation"] for x in r),
                  f"rerun {impl}: {sum(x['matches_expectation'] for x in r)} of {len(r)} rows match PREREG")

    print(f"{'OK' if not fails else 'FAILED'}: {len(fails)} failing checks")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
