#!/usr/bin/env python3
"""Fix-round A/A checks (FIX-PREREG.json aa_rerun) from the raw rows alone.

  --harness <fixed harness/ar>   primary + secondary checks -> --out
  --harness <old harness/ar> --g2-only   G2 of the calibrated evaluator on the same rows -> --out

usage (under hostless): analyze_aa.py --rows raw/*.jsonl --harness H --out checks.json [--g2-only]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", nargs="+", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--g2-only", action="store_true")
    a = p.parse_args()
    sys.path.insert(0, a.harness)
    from areval import aa, gates  # noqa: E402

    rows = [json.loads(x) for f in a.rows for x in Path(f).read_text().splitlines() if x.strip()]
    pre = {"invariants": {"expected_route": "accessibility", "expected_path": None}}
    g2 = gates.g2(rows, pre)
    out: dict = {"G2": {"pass": g2["pass"], "reasons": g2["reasons"][:6]}}
    if a.g2_only:
        Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
        print(json.dumps(out))
        return 0
    starts = {r["session"]: r for r in rows if r.get("schema") == "ar.session.v1" and r.get("event") == "start"}
    soak_sessions = sorted({r["session"] for r in gates.trials(rows, kind="soak")})
    paired_sessions = sorted({r["session"] for r in gates.trials(rows, kind="task") if r.get("pair_id")})
    dbus = {s: (starts[s].get("session_binds") or {}).get("dbus") for s in starts}
    s = aa.summarize(rows)
    w, t = s["whole_task_T"], s["T_act"]
    out.update({
        "primary_T_act_ci_includes_zero": t["ci_includes_zero"],
        "T_act": {k: t[k] for k in ("pairs", "sigma_ln", "delta_aa_ln", "ci95_ln", "tau", "n_pairs_required")},
        "whole_task": {k: w[k] for k in ("pairs", "sigma_ln", "delta_aa_ln", "ci95_ln", "ci_includes_zero", "tau")},
        "guardrail_check": {"whole_task_delta_aa_ln": w["delta_aa_ln"], "limit_ln": math.log1p(0.0311),
                            "pass": w["delta_aa_ln"] <= math.log1p(0.0311)},
        "live_F1": {"soak_sessions": soak_sessions, "paired_sessions": paired_sessions,
                    "soak_dbus_differs": all(dbus.get(x) not in {dbus.get(y) for y in paired_sessions}
                                             for x in soak_sessions),
                    "soak_rows_candidate_only": all(r["arm"] == "candidate" for r in gates.trials(rows, kind="soak")),
                    "every_session_has_binds": all(dbus.get(x) for x in starts)},
        "G3": s["gates_on_aa"]["G3"]["pass"], "G4": s["gates_on_aa"]["G4"]["pass"],
        "G5_false_keep_check": s["gates_on_aa"]["G5_false_keep_check"],
        "task_trials_verified": s["task_trials_verified"], "task_trials_attempted": s["task_trials_attempted"],
        "soak_verified": sum(1 for r in gates.trials(rows, kind="soak") if r.get("verified")),
        "soak_trials": len(gates.trials(rows, kind="soak")),
        "failures": s["failures"], "trace": s["trace"], "per_session": s["per_session"],
        "median_ms": {"T_base": w["base"]["median_ms"], "T_rebuild": w["rebuild"]["median_ms"],
                      "T_act_base": t["base"]["median_ms"], "T_act_rebuild": t["rebuild"]["median_ms"]},
        "loadavg_start": sorted(r["loadavg_start"][0] for r in gates.trials(rows, warmup=None))[::12],
    })
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: out[k] for k in ("primary_T_act_ci_includes_zero", "T_act", "whole_task", "guardrail_check",
                                          "live_F1", "G2", "G3", "G4")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
