#!/usr/bin/env python3
"""Write artifacts/ar/CALIBRATION2.json from the calibration-2 summary.json (run under hostless).

usage: make_artifact.py --summary summary.json --out CALIBRATION2.json --packet-commit SHA
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--packet-commit", required=True)
    p.add_argument("--verify", required=True, help="verify_artifacts.py result line")
    a = p.parse_args()
    s = json.loads(Path(a.summary).read_text())
    rows = [{"row": r["row"], "candidate": r["candidate"], "expect": r["expect"],
             "result": "PASS" if r["pass"] else "FAIL", "detail": r["detail"]} for r in s["rows"]]
    amend = [{"row": r["row"], "candidate": r["candidate"], "expect": r["expect"],
              "result": "PASS" if r["pass"] else "FAIL", "detail": r["detail"]} for r in s["amendment_rows"]]
    failed = [r["row"] for r in rows if r["result"] == "FAIL"]
    cal_ledger = [{k: e.get(k) for k in ("eval_id", "tag", "stage", "verdict", "failed_gate", "wall_s", "g0_s",
                                         "blocks", "held_s", "lock_wait_s")} for e in s["evaluations"]]
    out = {
        "schema": "ar.calibration_artifact.v2",
        "worker": "Phase 1 calibration 2 (evaluator agent; Claude Code workflow subagent). No provider of any kind; "
                  "scripted caller only; evaluator f56422868 unchanged.",
        "overall": "PASS" if s["overall_pass"] else "FAIL",
        "overall_reason": ("every pre-registered row R1-R10 passes" if s["overall_pass"] else
                           f"pre-registered rows failing: {', '.join(failed)}"),
        "rows_passed": f"{sum(1 for r in rows if r['result'] == 'PASS')}/{len(rows)}",
        "rows": rows,
        "amendment_rows": amend,
        "diagnostics_not_gate": s.get("diagnostics"),
        "tau": s["tau"], "decision_metric": s["metric"],
        "lord": s["lord"], "amendment_lord": s.get("amendment_lord"),
        "cost": s["cost"], "throughput": s["throughput"],
        "calibration_ledger": cal_ledger,
        "packet": {"branch": "exp/ar-harness-20261002", "commit": a.packet_commit, "pushed": False,
                   "dir": "docs/experiments/ar-calibration2-2026-10-02/", "verify": a.verify},
    }
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=False, default=str) + "\n")
    print(out["overall"], out["rows_passed"], [(r["row"], r["result"]) for r in amend])


if __name__ == "__main__":
    main()
