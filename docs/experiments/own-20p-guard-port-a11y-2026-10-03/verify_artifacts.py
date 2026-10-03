#!/usr/bin/env python3
"""OWN-20P packet verifier (stdlib + git). Run under bin/hostless: python3 verify_artifacts.py
(set CUA_PRIVACY_NAMES_FILE for the private-name check; see verify_helper.py).

Derived from the OWN-20G verifier (ce7544cc0). Checks:
 1. own20p-summary.json and own20p-trial-metrics.jsonl.gz recompute from raw/ (analyze.py, byte-identical);
 2. lock evidence: every counted block's trials fall inside a SHARED quiet-lane receipt for that
    block's label in raw/lock-ledger.jsonl (lane OWN-20P, pid, loadavg, rc), <= 10 trials per acquisition;
 3. PREREG order: the PREREG commit precedes the first counted trial and is an ancestor of HEAD;
    PREREG.json, plan.json, make_plan.py, run_all.sh, session_entry.sh and harness/ are unchanged since;
 4. every block ran the provenance sha256 of its two roles and the committed plan; 0 non-loopback connects;
 5. harness/ files are blob-identical to the OWN-20G packet (recorded blob ids; and against ce7544cc0
    when that commit is present);
 6. source: U0..G0 is one commit touching only focus_guard.rs; G0..GA is one commit (files listed);
    the detached trees are reconstructed with git plumbing: red = G0 minus raw/source/red-fix-only.patch,
    G0m libs/cua-driver = a30cbbc3b + raw/source/g0m-vs-own20g-g.patch, U0m libs/cua-driver = bdf33d9fe's;
 7. UNIT logs: red fails only the stall test; green A and GA pass the platform-linux lib with 0 failures;
 8. README cites every headline number and verdict listed in provenance.json;
 9. cited files tracked (verify_helper.check_cited) and privacy (verify_helper.check_privacy) on every
    tracked packet file and every commit cb685fad7..HEAD; commit identities and trailers.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_helper import check_cited, check_privacy  # noqa: E402

FAIL: list[str] = []
BASE = "cb685fad7aef1df6a35ffec653295a0cea4daee6"
FIX_FILE = "libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"
FROZEN = ["PREREG.json", "plan.json", "make_plan.py", "run_all.sh", "session_entry.sh", "harness"]
IDENTITY = "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>"
TRAILER = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def check(cond: bool, msg: str) -> None:
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def ts(value: str) -> int:
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    return int(datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).timestamp() * 1e9)


def git(*args: str, env: dict | None = None, check_rc: bool = True) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=check_rc,
                          env=env).stdout


def nested(d, path: str):
    for part in path.split("."):
        d = d[part]
    return d


def tree_after(base: str, patch: Path, reverse: bool = False) -> str:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        git("read-tree", base, env=env)
        args = ["apply", "--cached"] + (["-R"] if reverse else []) + [str(patch)]
        top = git("rev-parse", "--show-toplevel").strip()
        subprocess.run(["git", "-C", top, *args], check=True, env=env, capture_output=True)
        return git("write-tree", env=env).strip()


def main() -> None:
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    summary = json.loads((HERE / "own20p-summary.json").read_text(encoding="utf-8"))

    # 1. recompute
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        out, met = Path(tmp) / "s.json", Path(tmp) / "m.jsonl.gz"
        subprocess.run([sys.executable, str(HERE / "analyze.py"), "--raw", str(HERE / "raw"), "--out", str(out),
                        "--metrics", str(met)], check=True, capture_output=True)
        check(out.read_bytes() == (HERE / "own20p-summary.json").read_bytes(), "own20p-summary.json recomputes from raw/")
        check(gzip.decompress(met.read_bytes()) == gzip.decompress((HERE / "own20p-trial-metrics.jsonl.gz").read_bytes()),
              "own20p-trial-metrics.jsonl.gz recomputes from raw/")

    # 2 + 4. locks, binaries, plan, network
    plan = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256((HERE / "plan.json").read_bytes()).hexdigest()
    bins_of = {b["block"]: b["bins"] for b in plan["blocks"]}
    ledger = [json.loads(x) for x in (HERE / "raw" / "lock-ledger.jsonl").read_text(encoding="utf-8").splitlines()
              if x.strip()]
    intervals: dict[str, list] = {}
    for row in ledger:
        if "acquired" in row and "released" in row:
            intervals.setdefault(row["label"], []).append((ts(row["acquired"]), ts(row["released"]), row))
    sha_of = {role: v["sha256"] for role, v in prov["binaries"].items()}
    counted = set(prov["counted_labels"])
    first_counted = None
    seen_counted = set()
    for d in sorted((HERE / "raw").iterdir()):
        f = d / "trials.jsonl.gz"
        if not f.exists():
            continue
        rows = [json.loads(x) for x in gzip.open(f, "rt", encoding="utf-8") if x.strip()]
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        trials = [r for r in rows if r.get("event") == "trial"]
        block = meta.get("block")
        iv = intervals.get(d.name, [])
        inside = bool(iv) and all(any(a <= t["w_begin"] and t.get("w_end", t["w_begin"]) <= b for a, b, _ in iv)
                                  for t in trials)
        shared = bool(iv) and all(r.get("mode") == "shared" and r.get("lane") == "OWN-20P"
                                  and {"pid", "loadavg_at_acquire", "rc"} <= set(r) for *_, r in iv)
        check(inside and shared and len(trials) <= 10,
              f"{d.name}: {len(trials)} trials inside a shared OWN-20P lock receipt (<= 10 per acquisition)")
        roles = bins_of.get(block) if not d.name.startswith("own20p-pilot") else None
        if roles:
            want = {"U": sha_of[roles["U"]], "G": sha_of[roles["G"]]}
            check(meta.get("driver_sha256") == want, f"{d.name}: ran {roles['U']}/{roles['G']} at the provenance sha256")
            check(meta.get("plan_sha256") == plan_sha, f"{d.name}: plan sha256 matches plan.json")
        end = next((r for r in rows if r.get("event") == "end"), None)
        check(((end or {}).get("net") or {}).get("refused_non_loopback_connects") == 0,
              f"{d.name}: 0 non-loopback connects (provider cap 0)")
        if trials and d.name in counted:
            seen_counted.add(d.name)
            w0 = min(t["w_begin"] for t in trials)
            first_counted = w0 if first_counted is None else min(first_counted, w0)
    check(seen_counted == counted, f"every counted label has raw trials ({len(seen_counted)}/{len(counted)})")

    # 3. PREREG order and frozen files
    pre = prov["prereg_commit"]
    check(first_counted is not None and ts(pre["committed_utc"]) < first_counted,
          f"PREREG commit {pre['committed_utc']} precedes the first counted trial")
    try:
        subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", pre["sha"], "HEAD"], check=True)
        check(True, "PREREG commit is an ancestor of HEAD")
        changed = [n for n in FROZEN if git("diff", "--name-only", pre["sha"], "HEAD", "--", n).strip()]
        check(not changed, f"PREREG.json, plan, orchestration and harness/ unchanged since PREREG ({changed})")
        later = git("diff", "--stat", pre["sha"], "HEAD", "--", "analyze.py").strip()
        print(f"info analyze.py changes since PREREG: {later.splitlines()[-1] if later else 'none'}")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        check(False, f"PREREG git checks: {exc}")

    # 5. harness blobs
    blobs = json.loads((HERE / "PREREG.json").read_text(encoding="utf-8"))["harness"]["blob_identical"]
    for name, blob in blobs.items():
        check(git("hash-object", str(HERE / "harness" / name)).strip() == blob, f"harness/{name} blob {blob[:12]}")
    if git("cat-file", "-t", "ce7544cc0", check_rc=False).strip() == "commit":
        for name, blob in blobs.items():
            src = git("rev-parse", f"ce7544cc0:docs/experiments/own-20g-guard-final-diff-2026-10-03/{name}").strip()
            check(src == blob, f"harness/{name} equals the OWN-20G packet file at ce7544cc0")

    # 6. source
    try:
        s = prov["source"]
        files = git("diff", "--name-only", BASE, s["G0"]).split()
        n = len(git("rev-list", f"{BASE}..{s['G0']}").split())
        check(files == [FIX_FILE] and n == 1, f"U0..G0 is one commit touching only {FIX_FILE}")
        files = git("diff", "--name-only", s["G0"], s["GA"]).split()
        n = len(git("rev-list", f"{s['G0']}..{s['GA']}").split())
        check(n == 1 and files == s["GA_files"], f"G0..GA is one commit touching {len(files)} files")
        red = tree_after(s["G0"], HERE / "raw" / "source" / "red-fix-only.patch", reverse=True)
        check(red == s["red_tree"], f"red tree (G0 minus the fix hunk) = {s['red_tree'][:12]}")
        g0m = tree_after("a30cbbc3b230e8bad7d86ae1e89866d4f9cdd1af", HERE / "raw" / "source" / "g0m-vs-own20g-g.patch")
        check(git("rev-parse", f"{g0m}:libs/cua-driver").strip() == s["G0m_libs_tree"],
              f"G0m libs/cua-driver = OWN-20G G + the refinement patch = {s['G0m_libs_tree'][:12]}")
        check(git("rev-parse", "bdf33d9fe4d716033089244a6571db21934374d6:libs/cua-driver").strip() == s["U0m_libs_tree"],
              f"U0m libs/cua-driver = OWN-20G U's = {s['U0m_libs_tree'][:12]}")
        check(git("rev-parse", f"{BASE}:libs/cua-driver").strip() == s["base_libs_tree"],
              f"base libs/cua-driver tree {s['base_libs_tree'][:12]}")
    except (subprocess.CalledProcessError, FileNotFoundError, KeyError) as exc:
        check(False, f"source checks: {exc}")

    # 7. UNIT logs
    u = HERE / "raw" / "unit"
    red = (u / "unit-red.log").read_text(encoding="utf-8")
    green = (u / "unit-green-a.log").read_text(encoding="utf-8")
    ga = (u / "unit-ga.log").read_text(encoding="utf-8")
    check("a_steal_during_a_read_stalled_past_the_watch_is_seen ... FAILED" in red
          and s_in(red, "603 passed; 1 failed"), "red: the stall test fails, 603 others pass")
    check("test result: ok. 2 passed; 0 failed" in green and s_in(green, "test result: ok. 604 passed; 0 failed"),
          "green A: 2/2 settle tests, platform-linux lib 604 passed 0 failed")
    check(all(x in ga for x in prov["unit_ga_expect"]), f"GA: {prov['unit_ga_expect']}")

    # 8. README numbers
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for key in prov.get("readme_numbers", []):
        value = nested(summary, key)
        check(str(value) in readme, f"README cites {key} = {value}")

    # 9. cited files, privacy, identities
    cited = check_cited(HERE, "all")
    check(not cited, f"every cited file is tracked ({len(cited)} findings)"
          + (": " + "; ".join(f"{c['kind']} {c['path']}" for c in cited[:6]) if cited else ""))
    leaks = check_privacy(HERE, BASE)
    check(not leaks, f"privacy: tracked packet files and commits {BASE[:9]}..HEAD ({len(leaks)} findings)"
          + (": " + "; ".join(f"{x['kind']} {x.get('commit', 'checkout')} {x['where']}" for x in leaks[:6]) if leaks else ""))
    bad = []
    for c in git("rev-list", f"{BASE}..HEAD").split():
        lines = git("log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B", c).splitlines()
        if lines[0] != IDENTITY or lines[1] != IDENTITY or TRAILER not in lines:
            bad.append(c[:9])
    check(not bad, f"every branch commit has the lane identity and trailer ({bad})")
    print(f"\n{'PASS' if not FAIL else 'FAIL'}: {len(FAIL)} failing checks")
    sys.exit(1 if FAIL else 0)


def s_in(text: str, needle: str) -> bool:
    return needle in text


if __name__ == "__main__":
    main()
