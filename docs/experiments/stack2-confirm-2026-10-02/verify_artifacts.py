#!/usr/bin/env python3
"""Verify the stack2-confirm-2026-10-02 packet from committed files only (stdlib + git). Prints RESULT PASS/FAIL.

  python3 verify_artifacts.py            (run from this directory, inside a kvnloo/cua checkout)

Check groups:
  1 commit order: PREREG < first measured run; analysis code < freeze; freeze < every scorer ledger line
  2 workload: tasks sha == PREREG, byte-identical regeneration, oracle self-test PASS 142/142
  3 manifest: file hashes, content hash, counts
  4 oracle: re-running workload.py oracle on raw/runs reproduces every RUN verdict in dataset/runs.jsonl
  5 runs: every task RUN or NOT_RUN; isolation receipts ok; Hermes head b51c7a22 and clean; observer completeness
  6 examples: one turn example per RUN task, labels == not verified_success, request carries no prompt/family/oracle field
  7 analysis: re-running harness/analyze.py on raw/ reproduces raw/analysis/*.json byte for byte
  8 summary: summary.json numbers and verdict equal the analysis files
  9 ledger: every scoring process has a quiet-lane ledger line with rc 0
 10 hygiene: no local absolute paths, host name or non-noreply e-mail in committed text; SHA256SUMS
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

HERE = Path(__file__).resolve().parent
PREREG_COMMIT = "f11cd9d83381f2bc9a69da3bbfced3eb682fe6e2"
ANALYSIS_COMMIT = "821d895a4d12adcb9212e1381d47505e91b91275"
FREEZE_COMMIT_FILE = HERE / "raw" / "freeze_commit.txt"   # written by the commit after the freeze commit
HERMES_HEAD = "b51c7a222e7a0fb29d1da8933a6c08b956b86f61"
HOST_SHA16 = "c76d9da671ff244f"  # sha256(host name)[:16]
FAILS: list[str] = []
PASSES: list[str] = []


def check(group: str, ok: bool, msg: str) -> None:
    (PASSES if ok else FAILS).append(f"[{group}] {msg}")


def jl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True, check=True).stdout.strip()


def commit_time(c: str) -> float:
    return float(git("show", "-s", "--format=%ct", c))


def g1() -> None:
    freeze = FREEZE_COMMIT_FILE.read_text().strip()
    idx = [r for r in jl(HERE / "raw" / "collect" / "index.jsonl") if r.get("status") == "RUN"]
    first = min(ts(r["started_at"]) for r in idx)
    check("1", commit_time(PREREG_COMMIT) < first, f"PREREG commit precedes the first measured run ({len(idx)} RUN)")
    anc = subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", PREREG_COMMIT, ANALYSIS_COMMIT]).returncode == 0
    anc2 = subprocess.run(["git", "-C", str(HERE), "merge-base", "--is-ancestor", ANALYSIS_COMMIT, freeze]).returncode == 0
    check("1", anc and anc2, "PREREG -> analysis code -> freeze commit ancestry")
    files = git("show", "--name-only", "--format=", freeze).splitlines()
    check("1", any(f.endswith("dataset/MANIFEST.json") for f in files), "the freeze commit adds dataset/MANIFEST.json")
    ledger = jl(HERE / "raw" / "quiet-lane-ledger.confirm.jsonl")
    ft = commit_time(freeze)
    check("1", ledger and all(ts(e["acquired"]) > ft for e in ledger), f"all {len(ledger)} scorer ledger lines start after the freeze commit")
    last = max(ts(r["ended_at"]) for r in idx)
    check("1", last < ft, "collection ended before the freeze commit")


def g2() -> None:
    prereg = json.loads((HERE / "PREREG.json").read_text())
    tasks = HERE / "workload" / "tasks.jsonl"
    check("2", sha(tasks) == prereg["workload"]["tasks_sha256"], "tasks.jsonl sha256 == PREREG")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([sys.executable, str(HERE / "harness" / "workload.py"), "generate", tmp], check=True)
        check("2", (Path(tmp) / "tasks.jsonl").read_bytes() == tasks.read_bytes(), "workload regeneration byte-identical")
        p = subprocess.run([sys.executable, str(HERE / "harness" / "oracle_selftest.py"), str(tasks),
                            str(HERE / "workload" / "fixtures"), str(Path(tmp) / "st")], capture_output=True, text=True)
        res = json.loads(p.stdout)
        check("2", res["result"] == "PASS" and res["ideal_pass"] == 142, "oracle self-test PASS 142/142")


def g3() -> None:
    m = json.loads((HERE / "dataset" / "MANIFEST.json").read_text())
    for name, h in m["files"].items():
        check("3", sha(HERE / "dataset" / name) == h, f"dataset/{name} sha256 matches MANIFEST")
    ch = hashlib.sha256(json.dumps(m["files"], sort_keys=True).encode()).hexdigest()
    check("3", ch == m["content_sha256"], f"content_sha256 {ch[:12]} recomputed")
    runs = jl(HERE / "dataset" / "runs.jsonl")
    ev = jl(HERE / "dataset" / "events.jsonl")
    check("3", m["counts"] == {"tasks": len(runs), "run": sum(r["status"] == "RUN" for r in runs),
                               "not_run": sum(r["status"] != "RUN" for r in runs), "observer_rows": len(ev)},
          f"counts {m['counts']}")


def g4() -> None:
    sys.path.insert(0, str(HERE / "harness"))
    import workload  # noqa
    tasks = {t["task_id"]: t for t in jl(HERE / "workload" / "tasks.jsonl")}
    runs = [r for r in jl(HERE / "dataset" / "runs.jsonl") if r["status"] == "RUN"]
    mism = []
    for r in runs:
        v = workload.oracle(tasks[r["task_id"]], HERE / "raw" / "runs" / r["run_id"])["verified_success"]
        if v != r["verified_success"]:
            mism.append(r["task_id"])
    check("4", not mism, f"oracle re-run reproduces {len(runs) - len(mism)}/{len(runs)} verdicts (mismatches: {mism[:5]})")


def g5() -> None:
    runs = jl(HERE / "dataset" / "runs.jsonl")
    tasks = jl(HERE / "workload" / "tasks.jsonl")
    check("5", [r["task_id"] for r in runs] == [t["task_id"] for t in tasks], "runs.jsonl lists every task in order")
    run = [r for r in runs if r["status"] == "RUN"]
    bad = [r["task_id"] for r in run if not r["isolation"]["ok"]]
    check("5", not bad, f"isolation receipts ok in {len(run) - len(bad)}/{len(run)} runs {bad[:5]}")
    heads = {r["worktree_head"] for r in run}
    check("5", heads == {HERMES_HEAD} and all(r["worktree_clean"] for r in run), f"Hermes head {heads} clean")
    ev = jl(HERE / "dataset" / "events.jsonl")
    dropped = sum(int((e.get("fields") or {}).get("dropped_rows") or 0) for e in ev if e.get("event") == "observer_rows_dropped")
    check("5", dropped == 0, f"observer_rows_dropped total {dropped}")
    check("5", all(r.get("oracle_error") in (None, False) for r in run), "every RUN task has an oracle verdict row")
    stat = [r for r in run if not r["isolation"]["live_home_stat_unchanged"]]
    # Disclosed in README section 1: the live Hermes processes rewrite auth.json (mtime only); Hermes saw an empty tmpfs.
    only_auth_mtime = all(r["isolation"]["live_home_changed_entries"] == [{"entry": "auth.json", "size_changed": False}]
                          and r["isolation"]["live_hermes_home_entries"] == "0" for r in stat)
    check("5", only_auth_mtime and len(stat) <= 1,
          f"live Hermes home file entries unchanged in {len(run) - len(stat)}/{len(run)} runs; the rest: auth.json mtime "
          f"only, no size change, live home an empty tmpfs inside Hermes ({[r['task_id'] for r in stat]})")


def g6() -> None:
    runs = {r["task_id"]: r for r in jl(HERE / "dataset" / "runs.jsonl") if r["status"] == "RUN"}
    ex = jl(HERE / "raw" / "examples" / "turn-examples.jsonl")
    check("6", sorted(e["identity"]["work_item_id"] for e in ex) == sorted(runs), f"{len(ex)} turn examples == RUN tasks")
    lab = all(e["verified_outcome"] == (None if runs[e["identity"]["work_item_id"]]["verified_success"] is None
                                        else runs[e["identity"]["work_item_id"]]["verified_success"] is False) for e in ex)
    check("6", lab, "turn labels == (oracle verdict is False); unknown stays unknown")
    allowed = {"harness", "provider", "model", "api_call_count", "api_error_count", "max_retry_count", "tool_call_count",
               "tool_error_count", "tools_used", "distinct_tool_count", "final_finish_reason", "execution_completed",
               "turn_exit_reason", "interrupted", "approx_input_tokens_max", "prompt_tokens_last", "output_tokens_total"}
    leak = [e["identity"]["work_item_id"] for e in ex if not set(e["request"]["state"]) <= allowed]
    check("6", not leak, "request state keys are the PREREG content-free counters only")


def g7() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for lane, qid in (("turn", "verification_needed"), ("api", "api.attempt_will_fail")):
            out = Path(tmp) / f"{lane}.json"
            subprocess.run([sys.executable, str(HERE / "harness" / "analyze.py"), str(HERE / "harness" / "vendor"), qid,
                            str(HERE / "raw" / "examples" / f"{lane}-examples.jsonl"), str(HERE / "raw" / "scored" / lane),
                            str(out)], check=True, capture_output=True)
            check("7", out.read_bytes() == (HERE / "raw" / "analysis" / f"{lane}-analysis.json").read_bytes(),
                  f"{lane} analysis reproduced byte for byte")


def g8() -> None:
    s = json.loads((HERE / "summary.json").read_text())
    t = json.loads((HERE / "raw" / "analysis" / "turn-analysis.json").read_text())
    a = json.loads((HERE / "raw" / "analysis" / "api-analysis.json").read_text())
    check("8", s["confirmatory"]["verdict"] == t["confirmatory_test"]["verdict"], f"verdict {s['confirmatory']['verdict']}")
    check("8", s["confirmatory"] == t["confirmatory_test"], "summary.confirmatory == turn analysis confirmatory_test")
    ok = all(abs((s["turn_rows"][k]["brier"] or 0) - (t["rows"][k].get("brier") or 0)) < 1e-12 for k in s["turn_rows"])
    check("8", ok, "summary turn-row Brier scores == analysis")
    check("8", s["api_lane"]["degenerate"] == a["G2"]["degenerate"] and s["api_lane"]["n_positive"] == a["n_positive"],
          f"api lane degenerate={a['G2']['degenerate']} positives={a['n_positive']}")


def g9() -> None:
    ledger = jl(HERE / "raw" / "quiet-lane-ledger.confirm.jsonl")
    labels = {e["label"] for e in ledger}
    scored = {f"confirm-score-{p.parent.name}-{p.stem.removeprefix('scored-')}" for p in (HERE / "raw" / "scored").glob("*/scored-*.jsonl")
              if not p.stem.startswith("scored-failopen")}
    check("9", scored <= labels, f"every scored row has a quiet-lane ledger line ({len(scored)} rows)")
    check("9", all(e["rc"] == 0 for e in ledger), "every ledger line rc 0")


def g10() -> None:
    files = git("ls-files", ".").splitlines()
    pat = re.compile("/" + "mnt/|(?<![>\\w])/" + "home/|/" + "workspace/|@(?!users\\.noreply\\.github\\.com)[a-z0-9-]+\\.(com|org|net)")
    hits = []
    for f in files:
        p = HERE / f
        if p.suffix in (".png", ".jpg", ".pyc") or not p.is_file() or f == "verify_artifacts.py":
            hits += [f"{f}: bytecode committed"] if p.suffix == ".pyc" else []
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(text):
            hits.append(f"{f}: {m.group(0)}")
        # the host name is checked by hash so it never appears in this file
        if any(hashlib.sha256(w.encode()).hexdigest()[:16] == HOST_SHA16 for w in set(re.findall(r"[a-z0-9]+", text.lower()))
               if len(w) == 5):
            hits.append(f"{f}: host name")
    check("10", not hits, f"no local paths/host/e-mail in {len(files)} committed files {hits[:5]}")
    sums = HERE / "SHA256SUMS"
    bad = [l.split("  ", 1)[1] for l in sums.read_text().splitlines() if sha(HERE / l.split("  ", 1)[1]) != l.split("  ", 1)[0]]
    check("10", not bad, f"SHA256SUMS ({len(sums.read_text().splitlines())} files) {bad[:5]}")


def main() -> None:
    for g in (g1, g2, g3, g4, g5, g6, g7, g8, g9, g10):
        try:
            g()
        except Exception as e:  # a crashed group is a failure, never a skip
            FAILS.append(f"[{g.__name__}] crashed: {type(e).__name__}: {e}")
    for line in PASSES:
        print("PASS", line)
    for line in FAILS:
        print("FAIL", line)
    print("RESULT", "PASS" if not FAILS else "FAIL")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
