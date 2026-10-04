#!/usr/bin/env python3
"""FRESH-07R: apply PREREG-P2's recertification gates (standard library only).

R2-10R (PREREG-P2 rows.R2-10R.gates): RECERT_PASS iff the default-off smoke (Phase 0 (d)), validity_100,
e4_zero, S_direction on every gated row and verdict_mapping all pass. The verdict comparison comes from
the ORIGINAL orig/r2-10r/recert_gates.py, run with a reference built from R2-10R's accepted
r2-10r-summary.json (c183b95e3). Its d1_digests and Phase 0 a/b/c/e gates are out of scope (PREREG-P2:
D1 and those Phase 0 rows are UNAFFECTED and not re-run). They are listed as not in scope and never
reported as passed.

N-04 (rows.N-04.gates): RECERT_PASS iff validity 100% in every measured cell, E4 0, S_best CI lower bound
> 1 on both tasks, the same verdicts as N-04's accepted summary (V; HCL per task; every E2 component
label of the primary reading per task), and the default-off smoke passes (R''n = R''). Also reported as
in N-04: untested share (primary and conservative readings; target < 5%) and the focus-steal row
(not gated).

usage: recert_p2.py r210r --summary <analyze_r2_10 out> --gates <recert_gates out> --phase0 <raw/phase0> --out <json>
       recert_p2.py n04 --summary <analyze_n04 out> --accepted <accepted n04-summary.json> --out <json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = ["checkbox", "text"]


def r210r(a: argparse.Namespace) -> dict:
    g = json.loads(Path(a.gates).read_text())
    sys.path.insert(0, str(HERE / "orig/r2-10r"))
    import analyze_r2_10  # noqa: E402
    d = analyze_r2_10.phase0(Path(a.phase0))["d_default_off"]
    in_scope = {"phase0_d_default_off": bool(d["pass"]), "validity_100": bool(g["validity_100"]["pass"]),
                "e4_zero": bool(g["e4_zero"]["pass"]), "S_direction": bool(g["S_direction"]["pass"]),
                "verdict_mapping": bool(g["verdict_mapping"]["pass"])}
    vm = g["verdict_mapping"]
    out = {"row": "R2-10R scripted + native (PREREG-P2 rows.R2-10R.gates)",
           "in_scope_gates": in_scope,
           "out_of_scope_not_rerun": {"d1_digests": "R2-10R D1 UNAFFECTED (FRESH-07 claims.json), not re-run",
                                      "phase0_a_b_c_e": "UNAFFECTED count rows on the CDP route, not re-run"},
           "disposition": "RECERTIFIED" if all(in_scope.values()) else "RECERT_FAIL",
           "failed": [k for k, v in in_scope.items() if not v],
           "S_direction": {"gated_n": g["S_direction"]["gated_n"], "gated_pass_n": g["S_direction"]["gated_pass_n"],
                           "changed": g["S_direction"]["changed"], "not_gated_changed": g["S_direction"]["not_gated_changed"]},
           "verdict_mapping": {"verdict_mismatches": vm["verdict_mismatches"],
                               "work_deleted_sign_flips": vm["work_deleted_sign_flips"],
                               "flagged_threshold_crossings": vm["flagged_threshold_crossings"],
                               "flagged_e2_status_changes": vm["flagged_e2_status_changes"],
                               "sign_rows": {k: v for k, v in vm["work_deleted_sign"].items() if not v["pass"]}},
           "changed_claims": [c for c in g["changed_claims"] if "d1_digests" not in c and "phase0" not in c]}
    return out


def n04(a: argparse.Namespace) -> dict:
    s = json.loads(Path(a.summary).read_text())
    acc = json.loads(Path(a.accepted).read_text())
    cells = s["gates"]["validity_95"]["cells"]
    validity = all(c["valid"] == c["n"] for c in cells.values()) and bool(cells)
    e4 = all(v == 0 for arm in s["e4"].values() for k, v in arm.items() if k != "rows")
    sdir = {t: s["e3"][t]["S_best"]["ci95"][0] > 1 for t in TASKS}
    verdicts_new = {"V": s["gates"]["V"]["verdict"], **{f"HCL/{t}": s["gates"][f"HCL/{t}"]["verdict"] for t in TASKS}}
    verdicts_acc = {"V": acc["gates"]["V"]["verdict"], **{f"HCL/{t}": acc["gates"][f"HCL/{t}"]["verdict"] for t in TASKS}}
    e2_mis = []
    for t in TASKS:
        cn = s["e2"][t]["primary_R2-10_reading"]["components"]
        ca = acc["e2"][t]["primary_R2-10_reading"]["components"]
        for c in sorted(set(cn) | set(ca)):
            vn, va = (cn.get(c) or {}).get("verdict"), (ca.get(c) or {}).get("verdict")
            if vn != va:
                e2_mis.append({"task": t, "component": c, "accepted": va, "new": vn})
    mapping = verdicts_new == verdicts_acc and not e2_mis
    smoke = bool(s.get("default_off_smoke_pass"))
    in_scope = {"validity_100": validity, "e4_zero": e4, "S_direction": all(sdir.values()),
                "verdict_mapping": mapping, "default_off_smoke": smoke}
    unt = {t: {"best_arm": s["e2"][t]["best_arm"],
               "primary": s["e2"][t]["primary_R2-10_reading"]["untested_share"],
               "conservative": s["e2"][t]["conservative_N-02_reading"]["untested_share"],
               "above_threshold_untested": s["e2"][t]["primary_R2-10_reading"]["above_threshold_untested"],
               "target_met_primary": s["e2"][t]["target_met_primary"],
               "accepted_primary": acc["e2"][t]["primary_R2-10_reading"]["untested_share"],
               "accepted_conservative": acc["e2"][t]["conservative_N-02_reading"]["untested_share"]} for t in TASKS}
    return {"row": "N-04 (PREREG-P2 rows.N-04.gates)", "in_scope_gates": in_scope,
            "disposition": "RECERTIFIED" if all(in_scope.values()) else "RECERT_FAIL",
            "failed": [k for k, v in in_scope.items() if not v],
            "S_best": {t: s["e3"][t]["S_best"] for t in TASKS}, "S_direction_per_task": sdir,
            "verdicts": {"new": verdicts_new, "accepted": verdicts_acc, "e2_component_mismatches": e2_mis},
            "untested_share": unt,
            "untested_share_gate_lt_5pct": {t: bool(unt[t]["primary"] is not None and unt[t]["primary"] < 0.05) for t in TASKS},
            "focus_steal_not_gated": s.get("focus_steal"), "v_control": s.get("v_control", {}).get("pass"),
            "invalid_cells": {k: c for k, c in cells.items() if c["valid"] != c["n"]}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["r210r", "n04"])
    ap.add_argument("--summary", required=True)
    ap.add_argument("--gates")
    ap.add_argument("--phase0")
    ap.add_argument("--accepted")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = r210r(a) if a.which == "r210r" else n04(a)
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("disposition", "failed", "in_scope_gates")}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
