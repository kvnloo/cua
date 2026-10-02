#!/usr/bin/env python3
"""DIAGNOSTIC ONLY (not the calibration verdict): re-run the unmodified pipeline (areval.gates.evaluate)
on the recorded confirm rows of every calibration evaluation, with exactly one evaluator change applied
at a time, to show which verdicts each known harness defect decides.

Variants:
  frozen        the evaluator as calibrated (must reproduce the ledger verdicts exactly)
  g2_dbus       G2 footprint normaliser also maps the per-session D-Bus socket name
                (/tmp/dbus-<random>, bound into the sandbox from the private session) to one entry
  g2_dbus+g7ci  g2_dbus, plus G7's trace-off check fails only when the bootstrap CI95 of
                (Delta_off - Delta_on) lies entirely outside [-ln(1+tau), ln(1+tau)]
  g2_dbus+g7ci+T_act  the same, with every gate reading T_act (first dispatch call -> verified done,
                the A/A fallback metric, areval.aa.t_act_ns) instead of whole-task T, and tau = 2.0%
                (the A/A T_act value)

LORD++ in every variant is replayed in ledger order from that variant's own G5 p-values.

usage (under hostless): diag.py --run-dir D --harness H/harness/ar --out diag.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from statistics import fmean


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    sys.path.insert(0, a.harness)
    from areval import gates, stats  # noqa: E402
    from areval.scanner import load_rules  # noqa: E402

    D = Path(a.run_dir)
    H = Path(a.harness)
    allow = json.loads((H / "allowlist.json").read_text())
    manifest = json.loads((H / "manifest.json").read_text())
    rules = load_rules()
    ledger = jl(D / "cal-results.jsonl")
    frozen_norm, frozen_g7 = gates._norm_file, gates.g7
    dbus = re.compile(r"^/tmp/dbus-[A-Za-z0-9]+$")

    def norm_dbus(path: str) -> str:
        return "/tmp/dbus-<session>" if dbus.match(path) else frozen_norm(path)

    def g7_ci(rows, prereg):
        res = frozen_g7(rows, prereg)
        reasons = [r for r in res["reasons"] if not r.startswith("trace_off_disagrees")]
        tau = prereg["tau"]["value"]
        on, off = gates.ln_pairs(gates.pairs(rows, "task", True)), gates.ln_pairs(gates.pairs(rows, "task", False))
        ci = None
        if len(on) >= 2 and len(off) >= 2:
            seed = prereg["design"]["seed"] + 11
            mo, mf = stats.bootstrap_means(on, 4000, seed), stats.bootstrap_means(off, 4000, seed + 1)
            diffs = sorted(f - o for o, f in zip(mo, mf))
            ci = [stats.quantile(diffs, 0.025), stats.quantile(diffs, 0.975)]
            lim = math.log1p(tau)
            if ci[0] > lim or ci[1] < -lim:
                reasons.append(f"trace_off_disagrees_ci:{ci}")
        res = dict(res)
        res["reasons"], res["pass"] = reasons, not reasons
        res["metrics"] = {**res["metrics"], "off_minus_on_ci95": ci}
        return res

    from areval.aa import t_act_ns  # noqa: E402

    def to_t_act(rows):
        out_rows = []
        for r in rows:
            if r.get("schema") == "ar.trial.v1" and r.get("T_ns"):
                t = t_act_ns(r)
                r = {**r, "T_ns": t} if t else {k: v for k, v in r.items() if k != "T_ns"}
            out_rows.append(r)
        return out_rows

    variants = {"frozen": (frozen_norm, frozen_g7, None, None), "g2_dbus": (norm_dbus, frozen_g7, None, None),
                "g2_dbus+g7ci": (norm_dbus, g7_ci, None, None),
                "g2_dbus+g7ci+T_act": (norm_dbus, g7_ci, to_t_act, 0.02)}
    out = {"schema": "ar.calibration_diag.v1", "note": __doc__.strip().splitlines()[0], "variants": {}}
    for vname, (norm, g7, transform, tau_override) in variants.items():
        gates._norm_file, gates.g7 = norm, g7
        prior: list[float] = []
        res = []
        for rec in ledger:
            e = D / "evals" / rec["eval_id"]
            prereg = json.loads((e / "prereg.json").read_text())
            rows = [r for f in sorted((e / "confirm" / "raw").glob("*.jsonl")) for r in jl(f)]
            if transform:
                rows = transform(rows)
            if tau_override:
                prereg = {**prereg, "tau": {**prereg["tau"], "value": tau_override}}
            build = jl(e / "g1.rows.jsonl")
            g0i = json.loads((e / "g0.inputs.json").read_text())
            ev = gates.evaluate(prereg, rows, build, g0i, allow, manifest, rules, prior)
            if ev["lord"]:
                prior.append(ev["lord"]["p_value"])
            gm = {g["gate"]: g for g in ev["gates"]}
            res.append({"eval_id": rec["eval_id"], "verdict": ev["verdict"], "failed_gate": ev["failed_gate"],
                        "reasons": (gm.get(ev["failed_gate"]) or {}).get("reasons", [])[:6],
                        "delta": ev["delta"], "ci95": ev["ci95"], "p_value": ev["p_value"],
                        "alpha_i": (ev["lord"] or {}).get("alpha_i"),
                        "g7": {k: gm["G7"]["metrics"].get(k) for k in ("share", "saving_ms", "phase_saving_ms",
                                                                       "abs_on_off", "pairs_on", "pairs_off",
                                                                       "off_minus_on_ci95")} if "G7" in gm else None,
                        "g8": gm["G8"]["metrics"] if "G8" in gm else None,
                        "gs": gm["GS"]["metrics"] if "GS" in gm else None,
                        "matches_ledger": (vname != "frozen") or (ev["verdict"] == rec["verdict"]
                                                                  and ev["failed_gate"] == rec["failed_gate"])})
        out["variants"][vname] = {"evaluations": res,
                                  "keeps": sum(1 for r in res if r["verdict"] == "KEEP"),
                                  "by_failed_gate": {g: sum(1 for r in res if r["failed_gate"] == g)
                                                     for g in sorted({str(r["failed_gate"]) for r in res})}}
    gates._norm_file, gates.g7 = frozen_norm, frozen_g7
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for v, info in out["variants"].items():
        print(v, info["keeps"], info["by_failed_gate"], [(r["eval_id"][-3:], r["verdict"], r["failed_gate"]) for r in info["evaluations"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
