#!/usr/bin/env python3
"""Re-check the Phase 1 calibration packet from its raw files.

    python3 verify_artifacts.py          # exit 0 when every check passes

Uses the standard library plus the evaluator's own pure functions (harness/ar/areval on this branch,
stdlib-only), so every verdict is recomputed by the code that produced it.

Checks:
  1. MANIFEST.sha256 matches every file it lists.
  2. Every evaluation block has a quiet-lane receipt with rc 0, and every planned trial has a raw row
     (or a recorded not_run event).
  3. Every screen verdict recomputes from the screen rows, the G0 verdict and the G1 rows.
  4. Every ledger line recomputes (areval.gates.evaluate, ledger order, LORD++ from earlier p-values),
     matches final.json, and the hash chain and LORD++ replay verify.
  5. The row PASS/FAIL table and the overall verdict recompute from the per-evaluation verdicts.
  6. The feedback positive control (R8) recomputes.
  7. No packet file contains an absolute host path.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from statistics import fmean, median

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
HARNESS = HERE.parents[2] / "harness" / "ar"
sys.path.insert(0, str(HARNESS))
from areval import gates, lord, results, stats  # noqa: E402
from areval.scanner import load_rules  # noqa: E402

FAILS: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def jl(path: Path) -> list[dict]:
    if path.suffix == ".gz":
        text = gzip.decompress(path.read_bytes()).decode()
    elif path.exists():
        text = path.read_text()
    else:
        return []
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def rows_of(d: Path) -> list[dict]:
    return [r for f in sorted(d.glob("*.jsonl.gz")) for r in jl(f)]


def main() -> int:
    # 1 manifest
    man = HERE / "MANIFEST.sha256"
    bad = []
    for line in man.read_text().splitlines():
        sha, rel = line.split(None, 1)
        f = HERE / rel.strip()
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            bad.append(rel)
    check(not bad, f"MANIFEST.sha256 matches its files ({len(bad)} mismatches)")

    receipts = {r["label"]: r for r in jl(RAW / "quiet-lane-receipts.jsonl")}
    prereg_cal = json.loads((RAW / "CALIB-PREREG.json").read_text())
    tau = prereg_cal["evaluator"]["tau"]
    allow = json.loads((HARNESS / "allowlist.json").read_text())
    manifest = json.loads((HARNESS / "manifest.json").read_text())
    rules = load_rules()

    finals = {}
    for e in sorted((RAW / "evals").iterdir()):
        f = json.loads((e / "final.json").read_text())
        finals[f["eval_id"]] = f
        # 2 receipts + row completeness
        blocks = jl(e / "screen" / "blocks.jsonl") + jl(e / "confirm" / "blocks.jsonl")
        miss = [b["label"] for b in blocks if b["label"] not in receipts or receipts[b["label"]]["rc"] != 0 or b["rc"] != 0]
        check(not miss, f"{e.name}: {len(blocks)} blocks, each with a quiet-lane receipt rc 0")
        for stage in ("screen", "confirm"):
            plan_p = e / f"{stage}-plan.json"
            if not plan_p.exists() or not (e / stage / "raw").exists():
                continue
            plan = json.loads(plan_p.read_text())
            ran = {b["session"] for b in jl(e / stage / "blocks.jsonl")}
            planned = {t["trial_id"] for s in plan["sessions"] if s["session"] in ran for t in s["trials"]}
            got = set()
            for r in rows_of(e / stage / "raw"):
                if r.get("schema") == "ar.trial.v1" or r.get("event") == "not_run":
                    got.add(r["trial_id"])
            check(planned == got, f"{e.name}/{stage}: every planned trial of the {len(ran)} run sessions has a row ({len(got)}/{len(planned)})")
        # 3 screen recompute
        if (e / "screen.json").exists():
            s = json.loads((e / "screen.json").read_text())
            pre = json.loads((e / "prereg.json").read_text())
            rows = rows_of(e / "screen" / "raw")
            g0 = json.loads((e / "g0.json").read_text())
            build = jl(e / "g1.rows.jsonl")
            failed = None
            for name, fn in (("G0", lambda: g0), ("G1", lambda: gates.g1(build, pre["g1_required_suites"])),
                             ("G2", lambda: gates.g2(rows, pre)), ("G3", lambda: gates.g3(rows)),
                             ("G4", lambda: gates.g4(rows))):
                if not fn()["pass"]:
                    failed = name
                    break
            d = gates.ln_pairs(gates.pairs(rows, "task"))
            if len(d) >= 2:
                lo, hi = stats.bootstrap_ci(d, 0.95, seed=s["seed"])
                ranks = fmean(d) <= -math.log1p(pre["tau"]["value"]) and hi < 0
                delta_ok = abs(fmean(d) - s["delta"]) < 1e-12
            else:
                ranks, delta_ok = False, s.get("delta") is None
            v = "REJECT" if failed else ("RANKS" if ranks else "REVERT")
            check(v == s["verdict"] and failed == s["failed_gate"] and delta_ok,
                  f"{e.name}: screen verdict {s['verdict']} recomputes")

    # 4 ledger recompute
    ledger_path = RAW / "cal-results.jsonl"
    ledger = jl(ledger_path)
    prior: list[float] = []
    for rec in ledger:
        e = RAW / "evals" / rec["eval_id"]
        pre = json.loads((e / "prereg.json").read_text())
        rows = rows_of(e / "confirm" / "raw")
        ev = gates.evaluate(pre, rows, jl(e / "g1.rows.jsonl"), json.loads((e / "g0.inputs.json").read_text()),
                            allow, manifest, rules, prior)
        if ev["lord"]:
            prior.append(ev["lord"]["p_value"])
        same = (ev["verdict"], ev["failed_gate"]) == (rec["verdict"], rec["failed_gate"]) == (
            finals[rec["eval_id"]]["verdict"], finals[rec["eval_id"]]["failed_gate"])
        check(same, f"{rec['eval_id']}: ledger verdict {rec['verdict']}/{rec['failed_gate']} recomputes")
    check(not results.verify_chain(ledger_path), "calibration ledger hash chain verifies")
    logged = [r["lord"] for r in ledger if r.get("lord")]
    rep = lord.replay([x["p_value"] for x in logged])
    check(all(abs(a["alpha_i"] - b["alpha_i"]) < 1e-12 and a["rejected"] == b["rejected"] for a, b in zip(logged, rep)),
          f"LORD++ replay matches the {len(logged)} logged tests")

    # 5 rows
    summ = json.loads((RAW / "summary.json").read_text())
    by: dict[str, list[dict]] = {}
    for f in finals.values():
        by.setdefault(f["name"], []).append(f)
    v = lambda n: [x["verdict"] for x in by.get(n, [])]  # noqa: E731
    g = lambda n: [x["failed_gate"] for x in by.get(n, [])]  # noqa: E731
    noop = [x for n in by if n.startswith("noop") for x in by[n]]
    g0r = lambda n: json.loads((RAW / "evals" / f"ar-20261002-cal-{n}-r01" / "g0.json").read_text())["reasons"]  # noqa: E731
    expect = {
        "R1": len(v("sleep20")) == 1 and v("sleep20")[0] != "KEEP",
        "R2": len(v("sleep50")) == 1 and v("sleep50")[0] != "KEEP",
        "R3": len(v("delete50")) == 10 and v("delete50").count("KEEP") >= 8,
        "R4": v("success-early") == ["REJECT"] and g("success-early") == ["G2"],
        "R5a": g("g0-frozen-item") == ["G0"], "R5b": g("g0-test-item") == ["G0"], "R5c": g("g0-trace-line") == ["G0"],
        "R6": g("g0-scanner") == ["G0"] and any(r.startswith("scanner:") for r in g0r("g0-scanner")),
        "R7": len(noop) == 10 and sum(1 for x in noop if x["verdict"] == "KEEP") <= 1,
    }
    fb = jl(RAW / "feedback" / "browser" / "raw" / "s0.jsonl.gz")
    ps = gates.pairs(fb, "spot_browser_fill_submit")
    d = gates.ln_pairs(ps)
    lo, hi = stats.bootstrap_ci(d, 0.95, seed=20280013)
    med = median((a["T_ns"] - c["T_ns"]) / 1e6 for a, c in ps)
    expect["R8"] = med >= 1000 and hi < -math.log1p(tau)
    for r in summ["rows"]:
        check(expect[r["row"]] == r["pass"], f"{r['row']} {r['candidate']}: {'PASS' if r['pass'] else 'FAIL'} recomputes")
    check(summ["overall_pass"] == all(expect.values()), f"overall {'PASS' if summ['overall_pass'] else 'FAIL'} recomputes")
    # 6 feedback
    b = summ["feedback"]["browser"]
    check(abs(b["median_on_minus_off_ms"] - med) < 1e-6 and abs(b["delta_off_vs_on"] - fmean(d)) < 1e-12,
          f"R8 feedback control recomputes (ON-OFF median {med:.0f} ms, Delta {fmean(d):.3f})")

    # 7 host paths
    pat = re.compile(r"/mnt/|/home/(?!trial/)[a-z]|/tmp/claude")
    hits = []
    for f in HERE.rglob("*"):
        if f.is_file() and f.name != "verify_artifacts.py":
            data = gzip.decompress(f.read_bytes()).decode() if f.suffix == ".gz" else f.read_text(errors="replace")
            if pat.search(data):
                hits.append(str(f.relative_to(HERE)))
    check(not hits, f"no absolute host path in packet files ({hits[:3]})")
    print(f"\n{len(FAILS)} failing checks")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
