#!/usr/bin/env python3
"""OWN-78A packet verifier (standard library only; run from a clone of the branch).

1. Recomputes own78a-summary.json from raw/ with analyze.py and requires byte equality.
2. Requires the headline numbers to appear verbatim in README.md.
3. Unit rows: U-PR 107/109 with exactly the two named TS failures; U-F 109/109, typecheck rc 0,
   Python OK; U-RED-F1 fails exactly the F1 tests.
4. Budget: ledger attempts/reached <= 24/30, budget.json agrees, every attempt went to
   api.typesafe.ai with status 200 and a request id; per-cell allowance never exceeded.
5. Validity: every block ok; Driver sha256; harness and launcher sha256 equal the PREREG commit's
   files; tree ids equal git's; <= 10 cells per block; each block ran inside its shared-lock window.
6. Ordering: the PREREG commit is an ancestor of HEAD and precedes every block start.
7. Privacy: every commit base..HEAD (harness/privacy_scan.py) and every raw file.
8. Every file README.md cites is tracked by git (template verify_helper.check_cited).

usage: python3 verify_artifacts.py [--base <sha>] [--skip-git]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
import analyze  # noqa: E402

PREREG_SHA = "99632b75fe0c05d909576739e7bbefbeb249c546"
EXAMPLES = "libs/cua-driver/examples/jev-use"
PACKET_REL = "docs/experiments/own-78a-abstain-isolation-4394-2026-10-03"
DRIVER_SHA256 = "19bad35248702fd42f6aa372f1f4bebe4ca3728d9be0f67287f1c186a0b47df9"
TREE_SHAS = {"pr": "039257811e0bbb2348c616c52562409923d2856f", "f": "61eec09092fd161f62651a890c882f276a642855",
             "pre": "2ca90d33857fdb4813ecc8d12c2058be7d4ebcc4"}
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="5107f3ccaef38f9f5c66708f1a633f6288bc5dc8")
    parser.add_argument("--skip-git", action="store_true")
    args = parser.parse_args()

    summary = analyze.analyse()
    committed = json.loads((HERE / "own78a-summary.json").read_text())
    check("summary recomputes from raw/", summary == committed)

    readme = (HERE / "README.md").read_text()
    arms, attr, money = summary["arms"], summary["attribution"], summary["budget"]
    headlines = [
        f"A0 abstain **{arms['A0']['abstain']}/5**", f"A1 correct-type **{arms['A1']['correct_type']}/5**",
        f"A2 correct-type **{arms['A2']['correct_type']}/5**", f"A3 correct-type **{arms['A3']['correct_type']}/5**",
        attr["verdict"], f"{money['attempts']} attempts / {money['reached']} reached",
        f"**Disposition: {summary['disposition']}.**",
    ]
    for arm in ("A0", "A1", "A2", "A3"):
        lo, hi = arms[arm]["p_type_range"]
        headlines.append(f"{lo:.2f}-{hi:.2f}")
    for text in headlines:
        check(f"README states '{text}'", text in readme)

    unit = summary["unit"]
    named = ["S1 uses the bounded browser request and reports s1 as the actual backend",
             "live and typesafe aliases report typesafe after a bounded decision"]
    check("U-PR: TS 107/109 with exactly the two named failures",
          unit["pr"]["ts"] == {"tests": 109, "pass": 107, "fail": 2} and sorted(unit["pr"]["ts_failing"]) == sorted(named))
    check("U-PR: Python OK", unit["pr"]["python_status"].startswith("OK"))
    check("U-F: TS 109/109, typecheck rc 0, Python OK", unit["unit_109_of_109_credential_free_on_F"])
    check("U-RED-F1: only the F1 tests fail",
          unit["red"]["ts_failing"] == [named[1]] and len(unit["red"]["python_failing"]) == 1
          and "test_typesafe_request_restores_runner_verified_page_state" in unit["red"]["python_failing"][0])
    for row in ("pr", "f", "red"):
        env = (HERE / "raw" / "unit" / row / "env.txt").read_text()
        check(f"unit {row}: no credential variables in the environment", "credential_env_present=0" in env)

    ledger = analyze.jsonl(HERE / "raw" / "provider-ledger.jsonl")
    check("budget within lane cap 24 reached / 30 attempts", money["reached"] <= 24 and money["attempts"] <= 30)
    check("budget.json agrees with the ledger", money["budget_file_agrees"])
    check("every attempt: api.typesafe.ai, 200, request id present",
          all(r["host"] == "api.typesafe.ai" and r["status"] == 200 and r["request_id_present"] for r in ledger))
    per_trial = {}
    for r in ledger:
        per_trial[r["trial"]] = per_trial.get(r["trial"], 0) + 1
    check("at most 1 provider request per dry-run trial", all(v <= 1 for v in per_trial.values()))

    prereg_time = None if args.skip_git else utc(git("log", "-1", "--format=%cI", PREREG_SHA).strip())
    locks = analyze.jsonl(HERE / "raw" / "locks.jsonl")
    for block in ("smoke", "L1", "L2", "L3"):
        v = json.loads((HERE / "raw" / block / "validity.json").read_text())
        end = json.loads((HERE / "raw" / block / "end.json").read_text())
        check(f"{block}: validity ok, Driver sha256, version recorded",
              v["ok"] and v["driver_sha256"] == DRIVER_SHA256 and v["driver_version_in_session"] == "cua-driver 0.31.0")
        check(f"{block}: <= 10 cells", len(v["plan"]) <= 10)
        lock = next((l for l in locks if l["label"] == f"own78a-{block}"), None)
        check(f"{block}: ran inside its shared-lock window", lock is not None and lock["mode"] == "shared"
              and utc(lock["acquired"]) <= utc(v["started_utc"]) and utc(end["ended_utc"]) <= utc(lock["released"]) + timedelta(seconds=1))
        for name, sha in TREE_SHAS.items():
            check(f"{block}: tree {name} matches {sha[:9]}", v["trees"][name]["ok"] and v["trees"][name]["sha"] == sha)
        if not args.skip_git:
            for fname, key in (("own78a_harness.py", "harness_sha256"), ("own78a_launcher.py", "launcher_sha256")):
                blob = subprocess.run(["git", "-C", str(HERE), "show", f"{PREREG_SHA}:{PACKET_REL}/harness/{fname}"],
                                      capture_output=True, check=True).stdout
                check(f"{block}: {fname} sha256 equals the PREREG commit's", hashlib.sha256(blob).hexdigest() == v[key])
            for name, sha in TREE_SHAS.items():
                check(f"{block}: tree id {name} equals git's",
                      v["trees"][name]["examples_tree_id"] == git("rev-parse", f"{sha}:{EXAMPLES}").strip())
            check(f"{block}: started after the PREREG commit", utc(v["started_utc"]) > prereg_time)

    if not args.skip_git:
        ancestor = subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", PREREG_SHA, "HEAD"]).returncode == 0
        check("PREREG commit is an ancestor of HEAD", ancestor)
        import privacy_scan
        ok, problems, note = privacy_scan.scan(args.base, str(HERE))
        check(f"privacy: every commit {args.base[:9]}..HEAD ({note})", ok, "; ".join(problems[:8]))
        import verify_helper
        findings = verify_helper.check_cited(HERE, "all")
        check("every file README or the summary cites is tracked (template verify_helper)", not findings,
              ", ".join(f"{f['path']} {f['kind']}" for f in findings[:8]))
    absolute = re.compile(r"(/home/|/mnt/|/Users/|/tmp/)")
    leaked = [str(p.relative_to(HERE)) for p in (HERE / "raw").rglob("*") if p.is_file() and absolute.search(p.read_text(errors="replace"))]
    check("raw/: no absolute local paths", not leaked, ", ".join(leaked[:5]))

    print(f"\n{len(FAILS)} failed" if FAILS else "\nALL CHECKS PASS")
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
