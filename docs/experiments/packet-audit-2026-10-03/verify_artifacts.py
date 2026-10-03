#!/usr/bin/env python3
"""Verifier for the 2026-10-03 packet audit (standard library only; run under bin/hostless).

Default checks (no network, no checkout):
  1. coverage: audit.json lists every pushed packet in packets.json, in order, each head confirmed by
     the recorded `git ls-remote origin` (raw/origin-heads-start.txt), and every repair in packets.json;
  2. heads: in --git <repo> (default: the repository holding this file) every audited and repair head
     exists, holds its packet directory, and holds the verifier blob recorded for it; every repair
     head descends from its pushed head, and its commit list equals the one privacy-scanned;
  3. outputs: every verifier output under raw/verifier-output/ hashes to its recorded sha256, its
     recorded rc matches `passed`, and no output carries an absolute path, host name or secret;
  4. summary and gates: recomputed from the per-packet results, equal to audit.json;
  5. cited files: every ignored-but-cited finding at a pushed head is repaired or triaged in
     cited-triage.json; no repair head cites an ignored file, and its untracked citations are triaged;
  6. template: ../_template/test_verify_helper.py passes (positive and negative controls);
  7. privacy: every file of this packet and every commit of this branch since upstream main;
  8. README: the per-head table rows equal audit.json.
--rerun: also clones (git clone --shared) every repair head into $TMPDIR, re-runs its
  verify_artifacts.py with the recorded flags and requires exit 0 and the recorded cited-file findings;
  --rerun-all does the same for every pushed head and requires the recorded exit status.

usage: verify_artifacts.py [--git <repo>] [--rerun | --rerun-all] [--ledger <quiet-lane-ledger.jsonl>]
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "_template"))
import audit_packets as AP  # noqa: E402
from verify_helper import check_cited  # noqa: E402

FAILS: list[str] = []
N = 0


def check(ok: bool, msg: str) -> None:
    global N
    N += 1
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        FAILS.append(msg)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def arg(name: str) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main() -> None:
    repo = Path(arg("--git") or git(HERE, "rev-parse", "--show-toplevel").stdout.strip())
    audit = json.loads((HERE / "audit.json").read_text())
    pk = json.loads((HERE / "packets.json").read_text())
    triage = json.loads((HERE / "cited-triage.json").read_text())
    pushed, repairs = audit["pushed"], audit["repairs"]

    # 1. coverage
    check([r["id"] for r in pushed] == [e["id"] for e in pk["pushed"]] and len(pushed) == 27,
          f"1a audit covers all {len(pk['pushed'])} pushed packets in packets.json order")
    remote = {}
    for line in (HERE / "raw" / "origin-heads-start.txt").read_text().splitlines():
        sha, _, ref = line.partition("\t")
        remote[ref.strip()] = sha.strip()
    bad = [r["id"] for r in pushed if not (r["head_confirmed"] and r["origin_sha"] == r["head"]
                                           == remote.get(f"refs/heads/{r['branch']}"))]
    check(not bad, f"1b every pushed head equals origin at audit start (raw/origin-heads-start.txt) {bad}")
    check([(r["id"], r["head"]) for r in repairs] == [(e["id"], e["head"]) for e in pk["repairs"]],
          f"1c audit lists every repair head in packets.json ({len(repairs)})")

    # 2. heads in the repository
    for r in pushed + repairs:
        head, pdir = r["head"], r["packet_dir"]
        exists = git(repo, "cat-file", "-e", f"{head}^{{commit}}").returncode == 0
        blob = git(repo, "rev-parse", f"{head}:{pdir}/verify_artifacts.py").stdout.strip()
        check(exists and git(repo, "cat-file", "-e", f"{head}:{pdir}").returncode == 0
              and blob == r["verifier"]["blob"], f"2a {r['id']} {head[:12]} holds {pdir} and verifier blob {blob[:12]}")
    for r in repairs:
        anc = git(repo, "merge-base", "--is-ancestor", r["base_pushed_head"], r["head"]).returncode == 0
        base = git(repo, "merge-base", r["head"], AP.UPSTREAM_MAIN).stdout.strip()
        commits = [c[:12] for c in git(repo, "rev-list", "--reverse", f"{base}..{r['head']}").stdout.split()]
        check(anc and commits == r["privacy"]["commits"],
              f"2b {r['id']} repair descends from pushed {r['base_pushed_head'][:12]}; {len(commits)} commits scanned")

    # 3. verifier outputs
    mach = AP.Machine([repo.resolve()])  # local directory names come from the checkout path, read at run time
    for r in pushed + repairs:
        v = r["verifier"]
        out = (HERE / v["output"]).read_text()
        check(hashlib.sha256(out.encode()).hexdigest() == v["output_sha256"] and (v["rc"] == 0) == v["passed"]
              and not {k: n for k, n in mach.hits(out).items() if k in AP.SEVERE or k.startswith("secret:")},
              f"3 {r['id']} output {v['output']} hash, rc {v['rc']} -> passed {v['passed']}, no private strings")

    # 4. summary and gates
    s = audit["summary"]
    failing = [r["id"] for r in pushed if not r["verifier"]["passed"]]
    new_commits = sorted({c for r in repairs for c in r["privacy"]["commits"]} - {c for r in pushed for c in r["privacy"]["commits"]})
    new_findings = [f for r in repairs for f in r["privacy"]["findings"] if f["commit"] in new_commits and f["category"] not in AP.INFO]
    check(s["pushed_packets"] == len(pushed) and s["pushed_verifier_pass"] == len(pushed) - len(failing)
          and s["pushed_verifier_fail"] == failing and s["new_commits"] == new_commits
          and s["new_commit_privacy_findings"] == [dict(f, id=r["id"]) for r in repairs for f in r["privacy"]["findings"]
                                                   if f["commit"] in new_commits and f["category"] not in AP.INFO],
          f"4a summary recomputes: {len(pushed) - len(failing)}/{len(pushed)} pushed verifiers pass, failing {failing}, "
          f"{len(new_commits)} new commits, {len(new_findings)} findings on them")
    gates = {
        "every_repaired_head_verifier_passes_from_clean_clone": all(r["verifier"]["passed"] for r in repairs),
        "audit_covers_every_pushed_packet": [r["id"] for r in pushed] == [e["id"] for e in pk["pushed"]]
        and all(r["head_confirmed"] for r in pushed),
        "zero_privacy_findings_on_new_commits": not new_findings,
        "every_failing_pushed_packet_has_a_repair": set(failing) <= {r["id"] for r in repairs},
    }
    check(gates == audit["gates"] and all(gates.values()), f"4b gates recompute and hold {gates}")

    # 5. cited files
    untriaged = [(r["id"], f["path"]) for r in pushed for f in r["cited_not_tracked"]
                 if f["kind"] == "ignored" and r["id"] not in {x["id"] for x in repairs}
                 and f["path"] not in triage.get(r["id"], {})]
    check(not untriaged, f"5a every ignored-but-cited path at a pushed head is repaired or triaged {untriaged}")
    bad = [(r["id"], f["path"]) for r in repairs for f in r["cited_not_tracked"]
           if f["kind"] == "ignored" or f["path"] not in triage.get(r["id"], {})]
    check(not bad, f"5b no repair head cites an ignored file; every untracked citation is triaged {bad}")

    # 6. template controls
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    t = subprocess.run([sys.executable, str(HERE.parent / "_template" / "test_verify_helper.py")],
                       capture_output=True, text=True, env=env)
    check(t.returncode == 0 and "OK" in t.stderr, "6 template helper UNIT controls pass (planted ignored/untracked file caught; clean packet passes)")

    # 7. privacy of this packet and this branch
    hits = {}
    for f in sorted(HERE.rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts:
            h = {k: n for k, n in mach.hits(f.read_text(errors="replace")).items() if k in AP.SEVERE or k.startswith("secret:") or k in ("local_dir_name", "tmp_path")}
            if h:
                hits[str(f.relative_to(HERE))] = h
    check(not hits, f"7a privacy: packet files carry no absolute path, host name, local directory name, temp path or secret {hits}")
    head = git(HERE, "rev-parse", "HEAD").stdout.strip()
    pv = AP.privacy(HERE, head, mach, {})
    severe = [f for f in pv["findings"] if f["category"] in AP.SEVERE or f["category"].startswith("secret:") or f["category"] == "local_dir_name"]
    check(not severe and all("7121943+kvnloo@users.noreply.github.com" in i for i in pv["identities"]),
          f"7b privacy: {pv['commits_scanned']} branch commits since upstream main clean; identities {pv['identities']} {severe[:3]}")

    # 8. README tables carry every audited and repair head as recorded
    readme = (HERE / "README.md").read_text()
    missing = [r["id"] for r in pushed + repairs if AP.readme_row(r) not in readme]
    check(not missing, f"8 README rows equal audit.json for all {len(pushed)} pushed and {len(repairs)} repair heads {missing}")

    # rerun
    if "--rerun" in sys.argv or "--rerun-all" in sys.argv:
        targets = repairs + (pushed if "--rerun-all" in sys.argv else [])
        work = Path(tempfile.mkdtemp(prefix="pkt-audit-rerun-"))
        try:
            for r in targets:
                c = work / f"{r['id']}-{r['head'][:8]}"
                subprocess.run(["git", "clone", "-q", "--shared", "--no-checkout", str(repo), str(c)], check=True)
                git(c, "checkout", "-q", "-B", r["branch"], r["head"])
                pkt = c / r["packet_dir"]
                real = []
                shown = r["verifier"]["args"]
                for i, a in enumerate(shown):
                    if a == "<clone>":
                        real.append(str(c))
                    elif a == "<host>":
                        real.append(socket.gethostname())
                    elif a == "<quiet-lane-ledger>":
                        real.append(arg("--ledger") or "")
                    elif i and shown[i - 1] == "--git-range":
                        base = git(c, "merge-base", "HEAD", AP.UPSTREAM_MAIN).stdout.strip()
                        real.append(f"{base}..HEAD")
                    else:
                        real.append(a)
                tmp = c.parent / f"tmp-{c.name}"
                tmp.mkdir()
                p = subprocess.run([sys.executable, "verify_artifacts.py", *real], cwd=pkt, capture_output=True, text=True,
                                   env={**env, "TMPDIR": str(tmp), "PYTHON_COLORS": "0"}, timeout=1800)
                want = 0 if r in repairs else r["verifier"]["rc"]
                cited = check_cited(pkt, "all")
                cited_ok = cited == r["cited_not_tracked"]
                tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
                check(p.returncode == want and cited_ok,
                      f"R {r['id']} {r['head'][:12]} re-run from a clean clone: rc {p.returncode} (want {want}); "
                      f"cited-not-tracked {len(cited)}; {mach.scrub(tail[0].replace(str(c), '<clone>'))[:120]}")
                shutil.rmtree(c, ignore_errors=True)
                shutil.rmtree(tmp, ignore_errors=True)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    print(f"\n{N - len(FAILS)}/{N} checks passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
