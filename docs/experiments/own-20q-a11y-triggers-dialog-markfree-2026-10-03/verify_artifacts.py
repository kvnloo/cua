#!/usr/bin/env python3
"""OWN-20Q packet verifier (stdlib + git). Run under bin/hostless: python3 verify_artifacts.py
(set CUA_PRIVACY_NAMES_FILE for the private-name check; see verify_helper.py, blob-identical to OWN-20P's).

Derived from the OWN-20P verifier (64081dded). Checks:
 1. own20q-summary.json and own20q-trial-metrics.jsonl.gz recompute from raw/ (analyze.py, byte-identical);
 2. lock evidence: every counted block's trials fall inside one SHARED quiet-lane receipt for that block's
    label in raw/lock-ledger.jsonl (lane OWN-20Q, pid, loadavg, rc), <= 10 trials and <= 300 s per
    acquisition, and >= 30 s between this lane's consecutive counted acquisitions;
 3. PREREG order: the PREREG commit precedes the first counted trial and is an ancestor of HEAD;
    PREREG.json, plan.json, make_plan.py, run_all.sh, session_entry.sh and harness/ are unchanged since;
 4. every block ran the PREREG sha256 of its two roles and the committed plan; 0 non-loopback connects;
 5. the OWN-20G/OWN-20P harness files are blob-identical (PREREG ids, and the OWN-20P packet at 64081dded);
 6. source: 64081dded..31318e374 touches only atspi/native.rs, 31318e374..4ac191a7c only
    input/focus_guard.rs, GA's and GQ's libs/cua-driver differ in exactly those two files
    (raw/source/gq-vs-ga.patch), 64081dded's libs/cua-driver = GA's, and the red tree is GQ with
    raw/source/red-vs-green.patch applied;
 7. UNIT logs: red fails exactly the two new tests (platform-linux lib 609 passed, 2 failed); GQ passes
    both and the platform-linux lib with 0 failures;
 8. README cites every headline number listed in provenance.json;
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
OWN20P = "64081dded4e0a3ddf144e68ab1ea43579f85f572"
OWN20P_DIR = "docs/experiments/own-20p-guard-port-a11y-2026-10-03"
NATIVE = "libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs"
GUARD = "libs/cua-driver/rust/crates/platform-linux/src/input/focus_guard.rs"
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


def tree_after(base: str, patch: Path) -> str:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        git("read-tree", base, env=env)
        top = git("rev-parse", "--show-toplevel").strip()
        subprocess.run(["git", "-C", top, "apply", "--cached", str(patch)], check=True, env=env, capture_output=True)
        return git("write-tree", env=env).strip()


def main() -> None:
    prov = json.loads((HERE / "provenance.json").read_text(encoding="utf-8"))
    prereg = json.loads((HERE / "PREREG.json").read_text(encoding="utf-8"))
    summary = json.loads((HERE / "own20q-summary.json").read_text(encoding="utf-8"))

    # 1. recompute
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
        subprocess.run([sys.executable, str(HERE / "analyze.py"), str(HERE), "--out-dir", tmp], check=True,
                       capture_output=True)
        check((Path(tmp) / "own20q-summary.json").read_bytes() == (HERE / "own20q-summary.json").read_bytes(),
              "own20q-summary.json recomputes from raw/")
        check(gzip.decompress((Path(tmp) / "own20q-trial-metrics.jsonl.gz").read_bytes())
              == gzip.decompress((HERE / "own20q-trial-metrics.jsonl.gz").read_bytes()),
              "own20q-trial-metrics.jsonl.gz recomputes from raw/")

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
    sha_of = {role: v["sha256"] for role, v in prereg["binaries"].items() if isinstance(v, dict)}
    counted = set(prov["counted_labels"])
    first_counted = None
    seen_counted = set()
    acquisitions = []
    for d in sorted((HERE / "raw").iterdir()):
        f = d / "trials.jsonl.gz"
        if not f.exists():
            continue
        rows = [json.loads(x) for x in gzip.open(f, "rt", encoding="utf-8") if x.strip()]
        meta = next((r for r in rows if r.get("event") == "meta"), {})
        trials = [r for r in rows if r.get("event") == "trial"]
        block = meta.get("block")
        iv = intervals.get(d.name, [])
        inside = len(iv) == 1 and all(iv[0][0] <= t["w_begin"] and t.get("w_end", t["w_begin"]) <= iv[0][1]
                                      for t in trials)
        shared = len(iv) == 1 and iv[0][2].get("mode") == "shared" and iv[0][2].get("lane") == "OWN-20Q" \
            and {"pid", "loadavg_at_acquire", "rc"} <= set(iv[0][2])
        held_s = (iv[0][1] - iv[0][0]) / 1e9 if iv else None
        check(inside and shared and len(trials) <= 10 and held_s is not None and held_s <= 300,
              f"{d.name}: {len(trials)} trials inside one shared OWN-20Q receipt held {held_s and round(held_s)} s")
        if d.name in counted and iv:
            acquisitions.append((iv[0][0], iv[0][1], d.name))
        if d.name in counted:
            roles = bins_of.get(block)
            want = {"U": sha_of[roles["U"]], "G": sha_of[roles["G"]]} if roles else None
            check(bool(roles) and meta.get("driver_sha256") == want,
                  f"{d.name}: ran {roles and roles['U']}/{roles and roles['G']} at the PREREG sha256")
            check(meta.get("plan_sha256") == plan_sha, f"{d.name}: plan sha256 matches plan.json")
        end = next((r for r in rows if r.get("event") == "end"), None)
        check(((end or {}).get("net") or {}).get("refused_non_loopback_connects") == 0,
              f"{d.name}: 0 non-loopback connects (provider cap 0)")
        if trials and d.name in counted:
            seen_counted.add(d.name)
            w0 = min(t["w_begin"] for t in trials)
            first_counted = w0 if first_counted is None else min(first_counted, w0)
    check(seen_counted == counted, f"every counted label has raw trials ({len(seen_counted)}/{len(counted)})")
    acquisitions.sort()
    for name in prov.get("supplement_labels", []):
        iv = intervals.get(name, [])
        if iv:
            acquisitions.append((iv[0][0], iv[0][1], name))
    acquisitions.sort()
    gaps = {(a[2], b[2]): (b[0] - a[1]) / 1e9 for a, b in zip(acquisitions, acquisitions[1:])}
    short = {f"{a}->{b}" for (a, b), g in gaps.items() if g < 30.0}
    documented = set(prov["deviations"]["lock_gaps_under_30s"])
    check(bool(gaps) and short == documented and min(gaps.values()) >= 29.0,
          f">= 30 s between consecutive acquisitions except the documented {sorted(documented)} "
          f"(min {min(gaps.values(), default=0):.3f} s)")

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
    blobs = prereg["harness"]["blob_identical_from_own20p"]
    for name, blob in blobs.items():
        check(git("hash-object", str(HERE / name)).strip() == blob, f"{name} blob {blob[:12]}")
        if git("cat-file", "-t", OWN20P, check_rc=False).strip() == "commit":
            src = git("rev-parse", f"{OWN20P}:{OWN20P_DIR}/{name}").strip()
            check(src == blob, f"{name} equals the OWN-20P packet file at {OWN20P[:9]}")
    vh = git("hash-object", str(HERE / "verify_helper.py")).strip()
    check(vh == git("rev-parse", f"{OWN20P}:{OWN20P_DIR}/verify_helper.py", check_rc=False).strip(),
          "verify_helper.py is blob-identical to OWN-20P's")

    # 6. source
    try:
        s = prov["source"]
        check(git("diff", "--name-only", OWN20P, s["A2_fix"]).split() == [NATIVE]
              and git("rev-list", f"{OWN20P}..{s['A2_fix']}").split() == [s["A2_fix"]],
              "the A2 commit is one commit on the OWN-20P head touching only atspi/native.rs")
        check(git("diff", "--name-only", s["A2_fix"], s["GQ"]).split() == [GUARD]
              and git("rev-list", f"{s['A2_fix']}..{s['GQ']}").split() == [s["GQ"]],
              "the DLG commit is one commit touching only input/focus_guard.rs")
        check(git("rev-parse", f"{OWN20P}:libs/cua-driver").strip() == git("rev-parse", f"{s['GA']}:libs/cua-driver").strip(),
              "the branch base's libs/cua-driver is GA's")
        check(sorted(git("diff", "--name-only", s["GA"], s["GQ"], "--", "libs/cua-driver").split()) == sorted([NATIVE, GUARD]),
              "GA and GQ libs/cua-driver differ in exactly the two fixed files")
        ga_gq = tree_after(s["GA"], HERE / "raw" / "source" / "gq-vs-ga.patch")
        check(git("rev-parse", f"{ga_gq}:libs/cua-driver").strip() == s["GQ_libs_tree"],
              f"GA + raw/source/gq-vs-ga.patch = GQ libs/cua-driver {s['GQ_libs_tree'][:12]}")
        red = tree_after(s["GQ"], HERE / "raw" / "source" / "red-vs-green.patch")
        check(git("rev-parse", f"{red}:libs/cua-driver").strip() == s["red_libs_tree"],
              f"red = GQ + raw/source/red-vs-green.patch, libs/cua-driver {s['red_libs_tree'][:12]}")
        check(git("rev-parse", f"{BASE}:libs/cua-driver").strip() == s["base_libs_tree"],
              f"base libs/cua-driver tree {s['base_libs_tree'][:12]}")
    except (subprocess.CalledProcessError, FileNotFoundError, KeyError) as exc:
        check(False, f"source checks: {exc}")

    # 7. UNIT logs
    u = HERE / "raw" / "unit"
    red = (u / "unit-red.log").read_text(encoding="utf-8")
    green = (u / "unit-green.log").read_text(encoding="utf-8")
    names = ["a_steal_seen_before_the_active_window_follows_is_not_the_apps_dialog",
             "an_unanswered_call_keeps_the_bus_while_its_daemon_answers_and_loses_a_hung_one"]
    check(all(f"{n} ... FAILED" in red for n in names) and "609 passed; 2 failed" in red,
          "red: both new tests fail, platform-linux lib 609 passed 2 failed")
    check(all(f"{n} ... ok" in green for n in names) and "test result: ok. 611 passed; 0 failed" in green,
          "GQ: both new tests pass, platform-linux lib 611 passed 0 failed")

    # 8. README numbers
    readme = (HERE / "README.md").read_text(encoding="utf-8")
    for key in prov.get("readme_numbers", []):
        value = summary
        for part in key.split("|"):
            value = value[part]
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


if __name__ == "__main__":
    main()
