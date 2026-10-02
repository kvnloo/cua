#!/usr/bin/env python3
"""Calibration screen stage ("F1 screen"): does a candidate rank for a confirm run?

usage (under hostless):  screen.py --prereg P --rows R.jsonl [...] --build-rows G1.jsonl --g0 G0.json \
                                   --seed S --out screen.json

Pure function of the screen rows, the G0 verdict, the G1 rows and the pre-registration, built only
from the unmodified evaluator functions (areval.gates G1-G4, areval.stats):

  REJECT  at G0/G1/G2/G3/G4   the first of those gates that fails (same functions, same order);
  RANKS   G0-G4 pass and the paired ln-ratio Delta-hat <= -ln(1+tau) with bootstrap CI95 upper < 0;
  REVERT  otherwise (no credible improvement; the candidate is not sent to confirm).

The screen spends no LORD++ alpha and writes nothing to a results ledger: it is selection on data
that the confirm stage never reuses.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import fmean, median

AR = Path(__file__).resolve().parents[0]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--harness", required=True, help="harness/ar directory of the evaluator")
    p.add_argument("--prereg", required=True)
    p.add_argument("--rows", nargs="+", required=True)
    p.add_argument("--build-rows", required=True)
    p.add_argument("--g0", required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    sys.path.insert(0, a.harness)
    from areval import gates, stats  # noqa: E402

    prereg = json.loads(Path(a.prereg).read_text())
    rows = [json.loads(x) for f in a.rows for x in Path(f).read_text().splitlines() if x.strip()]
    build = [json.loads(x) for x in Path(a.build_rows).read_text().splitlines() if x.strip()]
    g0 = json.loads(Path(a.g0).read_text())
    tau = prereg["tau"]["value"]
    out: dict = {"schema": "ar.calibration_screen.v1", "eval_id": prereg["eval_id"], "seed": a.seed,
                 "tau": tau, "gates": []}
    failed = None
    for name, fn in (("G0", lambda: g0), ("G1", lambda: gates.g1(build, prereg["g1_required_suites"])),
                     ("G2", lambda: gates.g2(rows, prereg)), ("G3", lambda: gates.g3(rows)),
                     ("G4", lambda: gates.g4(rows))):
        res = fn()
        out["gates"].append({"gate": name, "pass": res["pass"], "reasons": res["reasons"][:20]})
        if not res["pass"]:
            failed = name
            break
    ps = gates.pairs(rows, "task")
    d = gates.ln_pairs(ps)
    out["n_pairs"] = len(d)
    if len(d) >= 2:
        lo, hi = stats.bootstrap_ci(d, 0.95, seed=a.seed)
        out.update(delta=fmean(d), ci95=[lo, hi], sigma_ln=stats.sd(d),
                   median_diff_ms=median((c["T_ns"] - b["T_ns"]) / 1e6 for b, c in ps),
                   median_T_ms={arm: gates._median_ms(gates.trials(rows, "task", arm))
                                for arm in ("champion", "candidate")})
        on, off = gates.pairs(rows, "task", trace=True), gates.pairs(rows, "task", trace=False)
        mech = prereg["mechanism"]
        spans = [(gates.span_ns(b, mech["start_mark"], mech["end_mark"]),
                  gates.span_ns(c, mech["start_mark"], mech["end_mark"])) for b, c in on]
        spans = [(x, y) for x, y in spans if x is not None and y is not None]
        if spans:
            out["mechanism_span_ms"] = {"champion_median": median(x for x, _ in spans) / 1e6,
                                        "candidate_median": median(y for _, y in spans) / 1e6,
                                        "pairs": len(spans)}
        out["pairs_trace_on_off"] = [len(on), len(off)]
    threshold = -math.log1p(tau)
    if failed:
        out.update(verdict="REJECT", failed_gate=failed, ranks=False)
    elif "delta" in out and out["delta"] <= threshold and out["ci95"][1] < 0:
        out.update(verdict="RANKS", failed_gate=None, ranks=True)
    else:
        out.update(verdict="REVERT", failed_gate=None, ranks=False)
    out["rank_rule"] = f"G0-G4 pass and delta <= {threshold:.5f} and ci95_hi < 0"
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: out.get(k) for k in ("eval_id", "verdict", "failed_gate", "n_pairs", "delta", "ci95",
                                              "median_diff_ms")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
