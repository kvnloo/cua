#!/usr/bin/env python3
"""Re-check the A/A packet from its raw rows alone (stdlib only; does not import the harness).

    python3 verify_artifacts.py            # exit 0 when every check passes

Checks:
  1. MANIFEST.sha256 matches every file it lists.
  2. Every A/A session has a quiet-lane receipt (rc 0) and every planned trial has a row.
  3. Every task trial (both arms) is oracle-verified once: seq_delta == 1, journal stamp <= done,
     one dispatch, route accessibility; every stale negative and impossible canary is refused
     with no mutation, in both arms and every session.
  4. The two arms are different binaries (base build vs rebuild of the same commit).
  5. An independent recomputation of sigma_ln, Delta_AA, the pair-resampled CI (includes 0),
     q97.5 |Delta_AA|, tau and n_pairs by power agrees with aa-summary.json (bootstrap
     quantities within a tolerance, closed-form quantities exactly).
  6. The browser spot check and the fixture-control validations meet their recorded pass counts.
  7. No packet file contains an absolute host path.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path
from statistics import NormalDist, fmean, stdev

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
FAILS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def boot_means(xs: list[float], batch: int, b: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    return [fmean(rng.choice(xs) for _ in range(batch)) for _ in range(b)]


def main() -> int:
    # 1. manifest
    for line in (HERE / "MANIFEST.sha256").read_text().splitlines():
        digest, name = line.split(None, 1)
        p = HERE / name.strip()
        check(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == digest, f"manifest {name.strip()}")

    summary = json.loads((HERE / "aa-summary.json").read_text())
    plan = json.loads((RAW / "aa" / "plan.json").read_text())
    rows = [r for f in sorted((RAW / "aa").glob("s*.jsonl")) for r in jsonl(f)]
    trials = [r for r in rows if r.get("schema") == "ar.trial.v1"]

    # 2. receipts and completeness
    receipts = jsonl(RAW / "aa" / "blocks.jsonl")
    ledger = jsonl(RAW / "aa" / "quiet-lane-receipts.jsonl")
    for s in plan["sessions"]:
        k = s["session"]
        check(any(r["session"] == k and r["rc"] == 0 for r in receipts), f"session {k}: block receipt rc 0")
        check(any(l["label"] == f"{plan['eval_id']}-s{k:03d}" and l["rc"] == 0 for l in ledger),
              f"session {k}: quiet-timed ledger line (exclusive lock) rc 0")
        got = {r["trial_id"] for r in trials if r["session"] == k}
        want = {t["trial_id"] for t in s["trials"]}
        check(got == want, f"session {k}: {len(got)}/{len(want)} planned trials have rows")

    # 3. correctness of every trial
    task = [r for r in trials if r["kind"] == "task"]
    bad = [r["trial_id"] for r in task if not (r.get("verified") and r.get("seq_delta") == 1
                                                and r.get("journal_before_done") and r.get("dispatch_calls") == 1
                                                and r.get("route") == "accessibility" and not r.get("failure"))]
    check(not bad, f"task trials verified once via accessibility: {len(task) - len(bad)}/{len(task)}")
    for kind in ("stale_negative", "impossible_canary"):
        ctl = [r for r in trials if r["kind"] == kind]
        okc = [r for r in ctl if r.get("refused") and not r.get("claimed_success") and r.get("seq_delta") == 0]
        per = {(r["session"], r["arm"]) for r in ctl}
        check(len(okc) == len(ctl) and len(per) == 2 * len(plan["sessions"]),
              f"{kind}: {len(okc)}/{len(ctl)} refused without mutation, every session x arm")

    # 4. two different binaries
    shas = plan["binaries_sha256"]
    check(shas["champion"] != shas["candidate"], "arms are two different builds of the same commit")
    check({r["binary_sha256"] for r in trials if r["arm"] == "champion"} == {shas["champion"]}
          and {r["binary_sha256"] for r in trials if r["arm"] == "candidate"} == {shas["candidate"]},
          "every row ran its arm's binary")

    # 5. independent recomputation
    by: dict[str, dict[str, dict]] = {}
    for r in task:
        if not r.get("warmup"):
            by.setdefault(r["pair_id"], {})[r["arm"]] = r
    pairs = [(p["champion"], p["candidate"]) for p in by.values() if len(p) == 2
             and p["champion"].get("verified") and p["candidate"].get("verified")]
    d = [math.log(c["T_ns"] / a["T_ns"]) for a, c in pairs]
    n = len(d)
    w = summary["whole_task_T"]
    sigma, delta = stdev(d), fmean(d)
    check(n == w["pairs"], f"complete pairs {n} == {w['pairs']}")
    check(abs(sigma - w["sigma_ln"]) < 1e-12, f"sigma_ln {sigma:.6f} == {w['sigma_ln']:.6f}")
    check(abs(delta - w["delta_aa_ln"]) < 1e-12, f"Delta_AA {delta:+.6f} == {w['delta_aa_ln']:+.6f}")
    means = boot_means(d, n, 4000, 99)
    lo, hi = quantile(means, 0.025), quantile(means, 0.975)
    tol = 0.25 * sigma / math.sqrt(n)
    check(abs(lo - w["ci95_ln"][0]) < tol and abs(hi - w["ci95_ln"][1]) < tol,
          f"CI95 [{lo:+.5f}, {hi:+.5f}] ~ [{w['ci95_ln'][0]:+.5f}, {w['ci95_ln'][1]:+.5f}]")
    check((lo <= 0 <= hi) == w["ci_includes_zero"],
          f"A/A CI includes 0 recorded as {w['ci_includes_zero']} (recomputed {lo <= 0 <= hi})")
    q = quantile([abs(x) for x in boot_means(d, n, 4000, 98)], 0.975)
    check(abs(q - w["abs_delta_aa_q975_ln"]) < tol, f"q97.5 |Delta_AA| {q:.5f} ~ {w['abs_delta_aa_q975_ln']:.5f}")
    tau = max(0.02, math.exp(w["abs_delta_aa_q975_ln"]) - 1)
    check(abs(tau - w["tau"]) < 1e-12, f"tau = max(2%, e^q - 1) = {tau:.5f}")
    z = NormalDist().inv_cdf(0.99) + NormalDist().inv_cdf(0.80)
    need = max(2, math.ceil(z * z * (sigma / math.log1p(tau)) ** 2))
    check(need == w["n_pairs_required"], f"n_pairs by power {need} == {w['n_pairs_required']}")
    metric = summary["decision_metric"]
    check(metric == ("whole_task_T" if need <= 400 else "T_act"), f"decision metric {metric} follows the 400-pair rule")

    # 5b. T_act (first dispatch -> done) and the same-binary A/A control
    def t_act(r: dict) -> int:
        first = next(c["m0"] for c in r["calls"] if c["tool"] in ("click", "set_value", "browser_type", "browser_click"))
        return r["t_done_ns"] - first
    da = [math.log(t_act(c) / t_act(a)) for a, c in pairs]
    ta = summary["T_act"]
    check(abs(stdev(da) - ta["sigma_ln"]) < 1e-12 and abs(fmean(da) - ta["delta_aa_ln"]) < 1e-12,
          f"T_act sigma {stdev(da):.5f} and Delta {fmean(da):+.5f} match")
    same = json.loads((HERE / "aa-same-summary.json").read_text())["whole_task_T"]
    srows = [r for f in sorted((RAW / "aa-same").glob("s*.jsonl")) for r in jsonl(f)
             if r.get("schema") == "ar.trial.v1" and r["kind"] == "task" and not r.get("warmup")]
    sby: dict[str, dict[str, dict]] = {}
    for r in srows:
        sby.setdefault(r["pair_id"], {})[r["arm"]] = r
    sd_ = [math.log(p["candidate"]["T_ns"] / p["champion"]["T_ns"]) for p in sby.values()
           if len(p) == 2 and p["champion"].get("verified") and p["candidate"].get("verified")]
    check(len(sd_) == same["pairs"] and abs(fmean(sd_) - same["delta_aa_ln"]) < 1e-12,
          f"same-binary A/A: {len(sd_)} pairs, Delta {fmean(sd_):+.5f} matches")
    check(len({r["binary_sha256"] for r in srows}) == 1, "same-binary A/A ran one binary in both arms")

    # 6. browser spot check and fixture controls
    spot = json.loads((RAW / "spot-and-controls.json").read_text())
    for name, cell in spot["cells"].items():
        check(cell["passed"] == cell["expected_passed"], f"{name}: {cell['passed']}/{cell['trials']} "
              f"(expected {cell['expected_passed']})")

    # 7. privacy
    leak = re.compile(r"/mnt/|/home/(?!trial\b)|/root/")  # /home/trial is the sandbox's own HOME
    for p in sorted(HERE.rglob("*")):
        if p.is_file() and p.name != "verify_artifacts.py":
            check(not leak.search(p.read_text(errors="replace")), f"no host path in {p.relative_to(HERE)}")

    print(f"\n{'PASS' if not FAILS else 'FAIL'}: {len(FAILS)} failing checks")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
