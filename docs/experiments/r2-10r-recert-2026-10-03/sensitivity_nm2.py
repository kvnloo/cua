#!/usr/bin/env python3
"""R2-10R native sensitivity to the external interference inside EXCLUSIVE block nm2 (standard library only).

Another workflow's verifier (bend-stack lane B389) ran a few seconds of single-core Python without the
quiet-lane lock at about 05:52:45-05:53:32Z on 2026-10-03, inside this lane's EXCLUSIVE window
r2-10r-a2-nm2 (05:51:37.630-05:54:27.287Z). This post-hoc, reporting-only check recomputes the four
gated native S rows (S0/X x checkbox/text) with the same S rule (analyze_r2_10.s_block, seeded bootstrap):

  nm1_only        rows of block nm1 only (rounds 0-11; the uncontaminated EXCLUSIVE block)
  drop_window     every round with a main nm2 trial whose [w_begin, w_end] overlaps the interference
                  window +/- 5 s is dropped (all arms of that round)

and reports per-arm T_oracle medians for nm1 vs nm2 and the 1-minute loadavg of the overlapping trials.
Each sensitivity row passes iff its CI excludes 1 on the same side as R2-10 (reference/r2-10-reference.json).

usage: sensitivity_nm2.py [--out nm2-sensitivity.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import analyze_r2_10 as A
import recert_gates as G

HERE = Path(__file__).resolve().parent
TASKS = ["checkbox", "text"]
ARMS = ("BASE", "S0", "X")
PAD_S = 5.0
WINDOW_UTC = ("2026-10-03T05:52:45Z", "2026-10-03T05:53:32Z")
LEDGER_NM2 = ("2026-10-03T05:51:37.630Z", "2026-10-03T05:54:27.287Z")


def ns(utc: str) -> int:
    return int(datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()) * 10**9


def load(raw: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    out = []
    for path in sorted((raw / "native").glob("nm*/trials.jsonl*")):
        for r in A.read_jsonl(path):
            if r.get("event") == "trial" and r.get("kind") == "main":
                out.append((r, {**A.native_row(r), "cls": r["task"]}))
    return out


def analyze(raw: Path) -> dict[str, Any]:
    ref = json.loads((HERE / "reference" / "r2-10-reference.json").read_text())
    pairs = load(raw)
    lo, hi = ns(WINDOW_UTC[0]) - int(PAD_S * 1e9), ns(WINDOW_UTC[1]) + int(PAD_S * 1e9)
    hit = [(r, row) for r, row in pairs if r["block"] == "nm2" and r["w_begin"] <= hi and r["w_end"] >= lo]
    drop = {(r["task"], r["round"]) for r, _ in hit}
    rows = [row for _, row in pairs]
    variants = {
        "nm1_only": [row for r, row in pairs if r["block"] == "nm1"],
        "drop_window": [row for r, row in pairs if (r["task"], r["round"]) not in drop],
    }
    out: dict[str, Any] = {
        "interference": {"source": "bend-stack SYNTHESIS.md section 9 (lane B389 verifier, unlocked single-core Python)",
                         "window_utc": list(WINDOW_UTC), "pad_s": PAD_S, "ledger_nm2_exclusive": list(LEDGER_NM2),
                         "nm2_trials_overlapping_window_pad": len(hit),
                         "nm2_trial_ids_overlapping": sorted(r["id"] for r, _ in hit),
                         "loadavg_1m_overlapping": [min(r["loadavg"][0] for r, _ in hit), max(r["loadavg"][0] for r, _ in hit)]
                         if hit else None,
                         "rounds_dropped": sorted([list(x) for x in drop])},
        "rows": {}, "medians_T_oracle_ms": {}}
    ok = True
    for v, vr in variants.items():
        for arm in ("S0", "X"):
            blk = A.s_block(vr, arm, TASKS)
            for t in TASKS:
                p = f"native.S.{arm}.{t}.all"
                cur = blk[t]["all"]
                rs, cs = G.side(ref["S"][p]["ci95"]), G.side(cur["ci95"])
                passed = cs == rs
                ok = ok and passed
                out["rows"].setdefault(v, {}).setdefault(arm, {})[t] = {"S": cur["S"], "ci95": cur["ci95"], "n": cur["n"],
                                                 "R2_10_side": rs, "side": cs, "pass": passed}
    worst = 0.0
    for t in TASKS:
        for a in ARMS:
            m = {b: statistics.median([row["T_oracle_ms"] for r, row in pairs if r["block"] == b and r["task"] == t
                                       and r["arm"] == a and row.get("valid") and row.get("T_oracle_ms") is not None])
                 for b in ("nm1", "nm2")}
            worst = max(worst, abs(m["nm1"] - m["nm2"]))
            out["medians_T_oracle_ms"][f"{t}/{a}"] = {**m, "abs_diff": abs(m["nm1"] - m["nm2"])}
    out["max_abs_median_diff_nm1_nm2_ms"] = worst
    out["n_main_rows"] = len(rows)
    out["rows_n"] = sum(len(x) for a in out["rows"].values() for x in a.values())
    out["pass"] = ok
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "nm2-sensitivity.json"))
    args = ap.parse_args()
    res = json.loads(json.dumps(analyze(HERE / "raw"), sort_keys=True))
    Path(args.out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: res[k] for k in ("pass", "max_abs_median_diff_nm1_nm2_ms")}
                     | {"overlap": res["interference"]["nm2_trials_overlapping_window_pad"],
                        "rows": {f"{v}.{a}.{t}": [round(r["S"], 4), [round(x, 4) for x in r["ci95"]], r["n"]]
                                 for v, av in res["rows"].items() for a, tv in av.items() for t, r in tv.items()}},
                     indent=1))


if __name__ == "__main__":
    main()
