#!/usr/bin/env python3
"""DIAGNOSTIC ONLY (not a calibration result): re-evaluate the recorded R3 (delete50) r01-r10 confirm
rows with the FIXED evaluator, in ledger order, on a fresh scratch LORD++ sequence.

Legacy rows predate the session manifest, so each raw file's ar.session.v1 start record gets the
session_binds the harness itself logged for that session: cua-x11-session.sh writes
"[session] DISPLAY=:N ... dbus=unix:path=<p>,guid=..." into the block log (logs/sNNN.log). The recorded
prereg gets the fix round's pre-registered fields (FIX-PREREG.json replay_diagnostic).

usage (under hostless): replay_r3.py --run-dir <calibration run dir, or the calibration packet's raw/>
                                      --harness <wt>/harness/ar --out replay.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

SESSION_LINE = re.compile(r"^\[session\] DISPLAY=:(\d+)\S* .*dbus=unix:path=([^,\s]+)", re.M)


def jl(path: Path) -> list[dict]:
    text = gzip.decompress(path.read_bytes()).decode() if path.suffix == ".gz" else path.read_text()
    return [json.loads(x) for x in text.splitlines() if x.strip()]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-dir", required=True)
    p.add_argument("--harness", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    sys.path.insert(0, a.harness)
    from areval import cli, gates, lord  # noqa: E402
    from areval.scanner import load_rules  # noqa: E402

    run = Path(a.run_dir)
    harness = Path(a.harness)
    allow = json.loads((harness / "allowlist.json").read_text())
    manifest = json.loads((harness / "manifest.json").read_text())
    rules = load_rules()
    prior: list[float] = []
    out = []
    for rep in range(1, 11):
        e = run / "evals" / f"ar-20261002-cal-delete50-r{rep:02d}"
        rows: list[dict] = []
        binds_found = 0
        for raw in sorted((e / "confirm" / "raw").glob("s*.jsonl*")):
            part = jl(raw)
            log = (e / "confirm" / "logs" / f"{raw.name.split('.')[0]}.log").read_text(errors="replace")
            m = SESSION_LINE.search(log)
            for r in part:
                if r.get("schema") == "ar.session.v1" and r.get("event") == "start" and m:
                    r["session_binds"] = {"x11": f"/tmp/.X11-unix/X{m.group(1)}", "dbus": m.group(2),
                                          "a11y": None, "xauthority": None}
                    binds_found += 1
            rows += part
        pre = json.loads((e / "prereg.json").read_text())
        pre["design"].update(metric="T_act", p_test=dict(cli.PTEST), n_pairs=37)
        pre["tau"]["value"] = 0.02
        pre["guardrail"] = {"metric": "T", "tau": 0.0311, "rule": "G6: whole-task mean paired ln ratio <= ln(1 + tau)"}
        pre["mechanism"]["trace_off_rule"] = "delta_off_within_ci95_on_widened_by_ln1p_tau"
        ev = gates.evaluate(pre, rows, jl(e / "g1.rows.jsonl"), json.loads((e / "g0.inputs.json").read_text()),
                            allow, manifest, rules, prior)
        if ev["lord"]:
            prior.append(ev["lord"]["p_value"])
        gm = {g["gate"]: g for g in ev["gates"]}
        pick = lambda g, keys: {k: gm[g]["metrics"].get(k) for k in keys} if g in gm else None  # noqa: E731
        out.append({
            "repeat": rep, "verdict": ev["verdict"], "failed_gate": ev["failed_gate"],
            "reasons": (gm.get(ev["failed_gate"]) or {}).get("reasons", [])[:4],
            "sessions_with_binds": binds_found, "delta_T_act": ev["delta"], "ci95": ev["ci95"],
            "p_value": ev["p_value"], "lord": ev["lord"],
            "G5": pick("G5", ("n_pairs", "p_resamples", "sigma_ln")),
            "G6": pick("G6", ("ln_ratio", "whole_task_delta", "whole_task_limit")),
            "G7": pick("G7", ("share", "delta_on", "delta_off", "trace_off_band", "pairs_off")),
            "G8": pick("G8", ("soak_trials", "required", "failures")),
            "GS": gm["GS"]["metrics"]["spot"] if "GS" in gm else None,
        })
        print(rep, ev["verdict"], ev["failed_gate"], out[-1]["reasons"][:1], flush=True)
    res = {"schema": "ar.fix_replay.v1", "note": __doc__.strip().splitlines()[0],
           "keeps": sum(1 for r in out if r["verdict"] == "KEEP"),
           "by_failed_gate": {str(g): sum(1 for r in out if r["failed_gate"] == g)
                              for g in sorted({r["failed_gate"] for r in out}, key=str)},
           "lord_levels": [lv["alpha_i"] for lv in lord.replay(prior)], "evaluations": out}
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(res["keeps"], res["by_failed_gate"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
