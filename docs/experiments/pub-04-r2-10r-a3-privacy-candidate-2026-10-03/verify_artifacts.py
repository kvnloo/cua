#!/usr/bin/env python3
"""PUB-04 packet verifier (standard library only; run under bin/hostless from a clean clone).

usage: verify_artifacts.py [--write-summary]
  Set CUA_PRIVACY_NAMES_FILE (untracked names file) for the full name check; CUA_REDACT_PATTERNS_FILE
  (untracked) additionally re-runs the masked normalized diff. Without them the host and user names are
  still checked and the pattern-free normalized diff still runs.

Recomputes pub04-summary.json from raw/ and requires it to equal the committed file, then checks:
  1. cited files: every packet path the README "Files" section and the summary cite is tracked by git;
  2. rewrite map: published -> candidate commits as PREREG.json registered, 25 redactions in 25 files
     (tmp-dbus only), 0 commit-message redactions, 0 manifest references;
  3. normalized diff (raw): every pair passes, masked and pattern-free; the note is the only addition;
     live (when the objects are present): the pattern-free diff recomputes and passes, and every commit
     after the candidate head touches only this packet;
  4. verifier parity: R2-10R a3 verify_artifacts.py gives the same N/M on the published head, the
     redaction-only head and the candidate head, with and without names; published vs redaction-only
     output is byte-identical; published vs candidate differs only in the commit/blob counters (+1, +1);
  5. candidate scan: 0 private findings on every commit; the published head has exactly the 25 tmp-dbus
     findings in 8be812d0c; the real-data restore control hits tmp-dbus once;
  6. scanner tests: red log = 11 failures, all in the url-encoded name class; green log = OK; the suite is
     re-run live and must pass;
  7. normalized-diff controls: masked mode fails all 5 tampered candidates; pattern-free fails 4 and
     passes the "unredacted file left" control (its known limit, covered by the scanner);
  8. rescan: 7 wave-6 heads equal the fetched live origin heads, 0 private findings on every commit;
     non-private findings are upstream content or the known public CI runner path;
  9. live privacy scan of every commit of this branch since the R2-10R base (pub04_scan): 0 private
     findings; non-private only the known CI runner path;
 10. shared quiet-lane lock receipts: 6, lane PUB-04, rc 0.
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
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE / "tools"))
from verify_helper import check_cited  # noqa: E402

RAW = HERE / "raw"
PUBLISHED = "d22eeb2ecf8a679d1425c21120a599775aa0817d"
CANDIDATE = "a2ded080cac3f8bdd17e3076da1e3b4196b57fa5"
REDACTED_ONLY = "a5ac8368fec372b06fedeb6cc9c6d6ab12e58dc2"
R2_10R_BASE = "0f1955d2f1ee2b01b40775aa53ea2af0b5544218"
NOTE = "docs/experiments/r2-10r-recert-2026-10-03/PRIVACY-REWRITE.md"
PACKET_REL = "docs/experiments/pub-04-r2-10r-a3-privacy-candidate-2026-10-03"
RUNNER_PATH = {("a0bca7440", ".github/workflows/ci-jev-use.yml"), ("6f438492b", ".github/workflows/ci-jev-use.yml"),
               ("b10cd09f2", ".github/workflows/ci-jev-use.yml")}
CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def j(rel: str):
    return json.loads((HERE / rel).read_text())


def git(*args: str, ok: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=ok)


def has(sha: str) -> bool:
    return git("cat-file", "-e", sha + "^{commit}", ok=False).returncode == 0


def checks_line(rel: str) -> str:
    m = re.search(r"^(\d+/\d+) checks passed$", (HERE / rel).read_text(), re.M)
    return m.group(1) if m else "missing"


def compute() -> dict:
    rw = j("raw/rewrite/rewrite-map.json")
    first = rw["commits"][0]
    nd_m, nd_p = j("raw/diff/normalized-diff-masked.json"), j("raw/diff/normalized-diff-patternfree.json")
    cand, pub = j("raw/scan/scan-candidate-a2ded080c.json")["rows"][0], j("raw/scan/scan-published-d22eeb2ec.json")["rows"][0]
    rs = j("raw/rescan/rescan-wave6-heads.json")
    ver = {f"{lab}.{mode}": checks_line(f"raw/verify/{lab}.{mode}.txt")
           for lab in ("o-d22eeb2ec", "r-a5ac8368f", "c-a2ded080c") for mode in ("nonames", "names")}
    return {
        "lane": "PUB-04",
        "published": {"branch": "exp/r2-10r-recert-a3-20261003", "head": PUBLISHED},
        "candidate": {"branch": "exp/r2-10r-recert-a3-r1c-20261003", "head": CANDIDATE, "redaction_only_head": REDACTED_ONLY,
                      "commit_map": {c["orig"]: c["new"] for c in rw["commits"]}},
        "redactions": {"files": len(first["files"]), "occurrences": sum(f["count"] for f in first["files"]),
                       "classes": sorted({k for f in first["files"] for k in f["by_class"]}),
                       "message_redactions": sum(c["message_count"] for c in rw["commits"]),
                       "manifest_refs": sum(len(f["manifest_refs"]) for c in rw["commits"] for f in c["files"])},
        "normalized_diff": {"pairs": len(nd_m["pairs"]), "masked_pass": nd_m["pass"], "patternfree_pass": nd_p["pass"],
                            "head_pair": {"identical_paths": nd_m["pairs"][-1]["identical_paths"],
                                          "differing_paths": nd_m["pairs"][-1]["differing_paths"],
                                          "redactions": nd_m["pairs"][-1]["redactions"], "added": nd_m["pairs"][-1]["added"]}},
        "verifier_parity": ver,
        "candidate_scan": {"commits": cand["commits_scanned"], "private_findings": cand["private_findings"],
                           "non_private": {k: v["findings"] for k, v in cand["counts"].items()}},
        "published_scan": {"commits": pub["commits_scanned"], "private_findings": pub["private_findings"],
                           "first_offending_commit": pub["first_offending_commit"]},
        "rescan": {"heads": len(rs["rows"]), "total_private_findings": rs["total_private_findings"],
                   "per_head": {r["lane"]: {"head": r["head"], "commits": r["commits_scanned"], "loop_commits": r["loop_commits"],
                                            "private": r["private_findings"]} for r in rs["rows"]}},
        "provider": {"typesafe_attempts": 0, "typesafe_reached": 0},
    }


def main() -> None:
    summary = compute()
    if "--write-summary" in sys.argv:
        (HERE / "pub04-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    check("pub04-summary.json recomputes identically from raw/", summary == j("pub04-summary.json"))
    readme = (HERE / "README.md").read_text()

    # 1 cited files
    missing = check_cited(HERE)
    check("cited files are tracked by git", not missing, str(missing[:5]))

    # 2 rewrite map
    pre = j("PREREG.json")["candidate"]["rewritten"]
    rw = summary["candidate"]["commit_map"]
    check("rewrite map = PREREG commit map", rw == pre, str(rw))
    r = summary["redactions"]
    check("25 redactions in 25 files, tmp-dbus only", (r["files"], r["occurrences"], r["classes"]) == (25, 25, ["tmp-dbus"]), str(r))
    check("0 commit-message redactions, 0 manifest references", r["message_redactions"] == 0 and r["manifest_refs"] == 0, str(r))

    # 3 normalized diff
    nd = summary["normalized_diff"]
    check("normalized diff (raw): 4 pairs pass, masked and pattern-free", nd["pairs"] == 4 and nd["masked_pass"] and nd["patternfree_pass"], str(nd))
    check("normalized diff (raw): head pair = 25 redacted paths, only the note added",
          nd["head_pair"]["differing_paths"] == 25 and nd["head_pair"]["redactions"] == 25 and nd["head_pair"]["added"] == [NOTE], str(nd["head_pair"]))
    if all(has(x) for x in (PUBLISHED, CANDIDATE, *rw, *rw.values())):
        pairs = [f"{a}:{b}" for a, b in rw.items()] + [f"{PUBLISHED}:{CANDIDATE}:{NOTE}"]
        top = git("rev-parse", "--show-toplevel").stdout.strip()
        out = Path(tempfile.gettempdir()) / f"pub04-nd-live-{os.getpid()}.json"
        p = subprocess.run([sys.executable, "-B", str(HERE / "tools" / "normalized_diff.py"), top, str(out), *pairs],
                           capture_output=True, text=True)
        check(f"normalized diff (live, masked check {'run' if os.environ.get('CUA_REDACT_PATTERNS_FILE') else 'not run'}) passes",
              p.returncode == 0, p.stdout[-400:] + p.stderr[-400:])
        out.unlink(missing_ok=True)
        if git("merge-base", "--is-ancestor", CANDIDATE, "HEAD", ok=False).returncode == 0:
            touched = [x for x in git("diff", "--name-only", CANDIDATE, "HEAD").stdout.split() if not x.startswith(PACKET_REL + "/")]
            check("every commit after the candidate head touches only this packet", not touched, str(touched[:5]))
    else:
        check("normalized diff (live): skipped, commits not in this clone (raw result stands)", True)

    # 4 verifier parity
    v = summary["verifier_parity"]
    check("R2-10R verifier: same N/M on published, redaction-only and candidate heads, both modes",
          len(set(v.values())) == 1 and all(n.split("/")[0] == n.split("/")[1] for n in v.values()), str(v))
    for mode in ("nonames", "names"):
        o = (RAW / f"verify/o-d22eeb2ec.{mode}.txt").read_text()
        rr = (RAW / f"verify/r-a5ac8368f.{mode}.txt").read_text()
        c = (RAW / f"verify/c-a2ded080c.{mode}.txt").read_text()
        check(f"R2-10R verifier ({mode}): published and redaction-only output byte-identical", o == rr)
        dl = [(a, b) for a, b in zip(o.splitlines(), c.splitlines()) if a != b]
        ok = len(o.splitlines()) == len(c.splitlines()) and len(dl) == 1
        if ok:
            ma = re.match(r"privacy: (\d+) commits, (\d+) blobs;(.*)$", dl[0][0])
            mb = re.match(r"privacy: (\d+) commits, (\d+) blobs;(.*)$", dl[0][1])
            ok = bool(ma and mb) and int(mb[1]) == int(ma[1]) + 1 and int(mb[2]) == int(ma[2]) + 1 and ma[3] == mb[3]
        check(f"R2-10R verifier ({mode}): candidate differs only by the note commit (+1 commit, +1 blob)", ok, str(dl[:2]))

    # 5 scans
    cs, ps = summary["candidate_scan"], summary["published_scan"]
    cand = j("raw/scan/scan-candidate-a2ded080c.json")["rows"][0]
    check("candidate scan: 0 private findings on every commit (17 commits, tip = candidate head)",
          cs["private_findings"] == 0 and all(p["private"] == 0 for p in cand["per_commit"]) and cand["tip"] == CANDIDATE
          and cs["commits"] == 17, str(cs))
    check("candidate scan: non-private findings only the 2 known CI runner path hits",
          cs["non_private"] == {"abs-path-generic": 2}
          and {p["commit"][:9] for p in cand["per_commit"] if p["counts"]} <= {"a0bca7440", "6f438492b"}, str(cs["non_private"]))
    pub = j("raw/scan/scan-published-d22eeb2ec.json")["rows"][0]
    check("published scan: exactly 25 tmp-dbus findings, all in 8be812d0c",
          pub["private_findings"] == 25 and all(d["kind"] == "tmp-dbus" and d["commit"] == "8be812d0c7cd" for d in pub["private_detail"]), str(ps))
    ctl = j("raw/controls/scan-control-restore.json")["rows"][0]
    check("scanner real-data control (one log restored): tmp-dbus x1", ctl["private_findings"] == 1
          and ctl["private_detail"][0]["kind"] == "tmp-dbus", str(ctl["counts"]))

    # 6 scanner tests
    red = (RAW / "unit/scanner-tests-red-before-fix.txt").read_text()
    green = (RAW / "unit/scanner-tests-green-after-fix.txt").read_text()
    fails = re.findall(r"^FAIL: .*$", red, re.M)
    blocks = [b for b in red.split("=" * 70)[1:] if b.lstrip().startswith("FAIL:")]
    url_only = len(blocks) == 11 and all("(case='url-" in b.splitlines()[1] or "'url-encoded'" in b for b in blocks)
    check("scanner tests red before fix: 11 failures, url-encoded class only",
          "FAILED (failures=11)" in red and len(fails) == 11 and url_only and "planted" not in " ".join(fails))
    check("scanner tests green after fix: 10 tests OK", re.search(r"^Ran 10 tests", green, re.M) is not None and green.rstrip().endswith("OK"))
    env = dict(os.environ, PYTHON_COLORS="0")
    t = subprocess.run([sys.executable, "-B", "-m", "unittest", "test_pub04_scan"], cwd=HERE / "tools", capture_output=True, text=True, env=env)
    check("scanner tests re-run live: OK", t.returncode == 0, t.stderr[-600:])

    # 7 normalized-diff controls
    rows = {}
    for line in (RAW / "controls/ctl-summary.txt").read_text().splitlines():
        m = re.match(r"control=(\S+) candidate=\S+ mode=(\S+) rc=(\d)", line)
        if m:
            rows[(m[1], m[2])] = int(m[3])
    names = ("extra", "unred", "rmpath", "addpath", "readme")
    check("controls: masked mode fails all 5 tampered candidates", all(rows.get((n, "masked")) == 1 for n in names), str(rows))
    check("controls: pattern-free fails 4, passes only the unredacted-file control (known limit)",
          all(rows.get((n, "patternfree")) == 1 for n in names if n != "unred") and rows.get(("unred", "patternfree")) == 0, str(rows))

    # 8 rescan
    rs = j("raw/rescan/rescan-wave6-heads.json")
    want = {ln.split()[0]: ln.split()[2] for ln in (RAW / "rescan/rescan-heads.txt").read_text().splitlines() if ln.strip()}
    live = {ln.split()[1].removeprefix("live/"): ln.split()[0] for ln in (RAW / "rescan/rescan-live-refs.txt").read_text().splitlines() if ln.strip()}
    br = {ln.split()[0]: ln.split()[1] for ln in (RAW / "rescan/rescan-heads.txt").read_text().splitlines() if ln.strip()}
    check("rescan: 7 heads, each equal to the fetched live origin head",
          len(rs["rows"]) == 7 and all(r["head"] == want[r["lane"]] == live[br[r["lane"]]] for r in rs["rows"]))
    check("rescan: 0 private findings on every commit of every head",
          rs["total_private_findings"] == 0 and all(p["private"] == 0 for r in rs["rows"] for p in r["per_commit"]))
    odd = [(p["commit"][:9], d["where"], d["kind"]) for r in rs["rows"] for p in r["per_commit"] for d in p["detail"]
           if not p["upstream_content"] and (p["commit"][:9], d["where"]) not in RUNNER_PATH]
    check("rescan: non-private findings are upstream content or the known CI runner path", not odd, str(odd[:5]))
    check("rescan headline in README", f"{rs['total_private_findings']} private findings" in readme)

    # 9 live privacy scan of this branch
    p = subprocess.run([sys.executable, "-B", "-c",
                        "import sys,json;sys.path.insert(0,'tools');import pub04_scan as P;from pathlib import Path;"
                        "top=P.git('.', 'rev-parse','--show-toplevel').strip();sc=P.Scanner(Path(top));"
                        f"c,f=P.scan_commits(top,['HEAD','--not','{R2_10R_BASE}'],sc,{{}});"
                        "print(json.dumps({'commits':len(c),'note':sc.note(),'f':[{k:x[k] for k in ('kind','commit','where')} for x in f]}))"],
                       cwd=HERE, capture_output=True, text=True)
    if p.returncode == 0:
        res = json.loads(p.stdout)
        priv = [x for x in res["f"] if x["kind"] not in ("abs-path-generic", "secret-like")]
        other = [x for x in res["f"] if x["kind"] in ("abs-path-generic", "secret-like") and (x["commit"][:9], x["where"]) not in RUNNER_PATH]
        print(f"live privacy scan: {res['commits']} commits; {res['note']}")
        check(f"live privacy scan of every commit since the R2-10R base ({res['commits']}): 0 private findings", not priv, str(priv[:5]))
        check("live privacy scan: non-private only the known CI runner path", not other, str(other[:5]))
    else:
        check("live privacy scan ran", False, p.stderr[-600:])

    # 10 lock receipts
    rec = [json.loads(x) for x in (RAW / "locks/shared-lock-receipts.jsonl").read_text().splitlines() if x.strip()]
    check("shared quiet-lane lock receipts: 6, lane PUB-04, rc 0", len(rec) == 6 and all(x["lane"] == "PUB-04" and x["rc"] == 0 for x in rec))

    # cited SHAs exist (when this clone has them)
    shas = set(re.findall(r"\b[0-9a-f]{40}\b", readme)) | {PUBLISHED, CANDIDATE, REDACTED_ONLY}
    absent = sorted(s for s in shas if not has(s))
    check(f"cited full SHAs present in this clone ({len(shas)})", not absent or os.environ.get("PUB04_ALLOW_ABSENT") == "1", str(absent[:6]))

    bad = [c for c in CHECKS if not c[1]]
    for name, ok, detail in CHECKS:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    print(f"{len(CHECKS) - len(bad)}/{len(CHECKS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
