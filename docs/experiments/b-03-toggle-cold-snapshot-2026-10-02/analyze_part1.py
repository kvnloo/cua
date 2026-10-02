"""B-03 Part 1: re-analysis of B-02 raw/ (no trials). Standard library only.

    python analyze_part1.py [--out part1-summary.json]

Decomposes the spec-literal best arm (lowest median T_oracle among arms whose validity
gates held, regardless of knob verdict: K5EV in every class) and the B-02 KEEP-only best
arm (K5V for fill/toggle, K5 for modal) for fill, toggle and modal, with B-02's component
rules (``analyze_browser.trial_row`` / ``arm_block`` and B-01's telescoping decomposition,
imported unchanged from the B-02 packet in this tree). Every component of at least 5% of
mean T_runner or at least 50 ms gets a verdict with its source packet:

- B-01R ``0cd63f786``: H_P, H_T, H_C, visualization, and the IRREDUCIBLE E2 rows
  (transport, post-dispatch, resolution, dispatch, verification reads).
- B-02 ``b282ff389``: H_E (endpoint), H_V (admission), H_W (cold first snapshot).

The untested share follows B-02's rule exactly: admission residual in V arms +
unattributed + the cold-first-snapshot excess where H_W is UNDECIDED.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
B02 = HERE.parent / "b-02-browser-driver-sites-2026-10-02"
sys.path.insert(0, str(B02))

import analyze_b02 as A2  # noqa: E402  (B-02 analysis, unchanged)
import analyze_browser as AB  # noqa: E402
import b01_analysis as B  # noqa: E402

SRC_B01 = "B-01R 0cd63f786 (exp/b-01r-browser-critpath-textfix-20261002)"
SRC_B02 = "B-02 b282ff389 (exp/b-02-browser-driver-sites-20261002)"

STATIC = {
    "decision": ("NOT_IN_SCOPE", "mock chooser; the live decision is measured in R2-10", "R2-10"),
    "resolution": ("IRREDUCIBLE", "ref resolution before dispatch", SRC_B01),
    "input_prep": ("IRREDUCIBLE", "trusted-input focus/selection proof", SRC_B01),
    "settles": ("OWNER_DECISION", "H_T: focus settle 0 on fill (insert_text replace site)", SRC_B01),
    "dispatch": ("IRREDUCIBLE", "the effectful CDP call", SRC_B01),
    "dispatch_post": ("IRREDUCIBLE", "CDP response handling", SRC_B01),
    "driver_post_dispatch": ("IRREDUCIBLE", "JSON-RPC result handling (E2 row: stdio + driver post-dispatch)", SRC_B01),
    "transport": ("IRREDUCIBLE", "stdio JSON-RPC (E2 row: stdio + driver post-dispatch)", SRC_B01),
    "client_validation": ("DELETED", "H_C KEEP: caller-compiled validators (already in K5)", SRC_B01),
    "runner_overhead": ("IRREDUCIBLE", "caller glue", SRC_B01),
    "verification_reads": ("IRREDUCIBLE", "independent oracle read; events are never the oracle", SRC_B01),
    "sleeps_polls": ("IRREDUCIBLE", "H_P: no material component (10 ms poll in K5)", SRC_B01),
    "target_effect_lag": ("IRREDUCIBLE", "target-owned", SRC_B01),
    "visualization": ("OWNER_DECISION", "feedback off in every arm (K1 fast glide KEEP); residual overlay/platform-gate bookkeeping", SRC_B01),
    "unattributed": ("UNTESTED", "unattributed", "-"),
}


def verdict_rows(cls: str, arm: str, b: dict[str, Any], ev: str, vv: str, wv: str, excess_mean: float) -> list[dict]:
    meanT = b["T_runner_ms"]["mean"]
    sub = b["sub_mean_ms"]
    rows = []
    for c in B.COMPONENTS:
        ms, share = b["components_mean_ms"][c], b["shares"][c]
        material = ms is not None and (ms >= AB.THRESH_MS or (share or 0) >= AB.THRESH_SHARE)
        parts: list[dict[str, Any]] = []
        if c == "observation":
            parts = [{"part": "one fresh semantic_v2 snapshot per action (base cost)",
                      "ms": ms - excess_mean, "verdict": "IRREDUCIBLE",
                      "why": "refs are never durable authority (#73); one fresh observation per action", "source": SRC_B01},
                     {"part": "cold-first-snapshot excess (snapshot1 - snapshot2)", "ms": excess_mean,
                      "verdict": wv.split(" (")[0], "why": wv, "source": SRC_B02}]
        elif c == "revalidate":
            ep = sub.get("reval_endpoint", 0.0)
            parts = [{"part": "owned-endpoint re-proof" + (" (bound check, E on)" if arm in AB.E_ARMS else " (full proof)"),
                      "ms": ep, "verdict": ev.split(" (")[0],
                      "why": "H_E: a cheaper ownership proof is a security policy call" if arm not in AB.E_ARMS else
                      "H_E: the remaining bound check is the reduced proof itself (E OWNER_DECISION)", "source": SRC_B02},
                     {"part": "remaining per-mutation binding re-proof steps", "ms": ms - ep, "verdict": "IRREDUCIBLE",
                      "why": "per-mutation re-proof (#73)", "source": SRC_B01}]
        elif c == "driver_pre_dispatch":
            res = sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0)
            parts = [{"part": "admission validation" + (" residual after V" if arm in AB.V_ARMS else " (two validations)"),
                      "ms": res, "verdict": "UNTESTED" if arm in AB.V_ARMS else vv.split(" (")[0],
                      "why": ("residual single validation incl. trace-mark cost" if arm in AB.V_ARMS else f"H_V {vv}"),
                      "source": SRC_B02},
                     {"part": "other pre-dispatch glue", "ms": ms - res, "verdict": "IRREDUCIBLE",
                      "why": "MCP pre-dispatch bookkeeping", "source": SRC_B01}]
        else:
            v, why, src = STATIC[c]
            parts = [{"part": c, "ms": ms, "verdict": v, "why": why, "source": src}]
        rows.append({"component": c, "mean_ms": ms, "share": share, "material": material,
                     "parts": parts if material else [], "verdict": (" + ".join(sorted({p["verdict"] for p in parts}))
                                                                      if material else "below threshold")})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "part1-summary.json"))
    a = ap.parse_args()
    raw = B02 / "raw"
    nv = A2.analyze_nv(raw)
    nv_files = A2._bundle_files(raw, "nv")
    nv_recs = [json.loads(t.splitlines()[-1]) for n, t in sorted(nv_files.items()) if n.endswith("-nv.jsonl")]
    nv_ref = nv_recs[0]["replies"] if (nv_recs and nv["pass"]) else None
    br = A2.browser(raw, nv_ref)
    measured = AB.load(raw, "measured")
    rows = [AB.trial_row(t) for t in measured]
    out: dict[str, Any] = {"schema": "cua.r2.b03.part1.v1", "evidence_class": "BENCHMARK (re-analysis of B-02 raw/measured, no new trials)",
                           "source_packet": SRC_B02, "trials": len(rows), "valid": sum(r["valid"] for r in rows),
                           "rule_spec_literal": "best arm = lowest median T_oracle among arms whose validity gates held (no knob-verdict filter)",
                           "rule_b02_keep_only": "best arm = lowest median T_oracle among arms whose knobs are all DELETED (KEEP) (B-02 E2 rule)",
                           "classes": {}}
    for cls in AB.CLASSES:
        c = br["measured"]["classes"][cls]
        ev, vv = c["E"]["verdict"], c["V"]["verdict"]
        wv = br["W"][cls]["amendment_rule_verdict"]
        cr = [r for r in rows if r["cls"] == cls]
        arms = {arm: AB.arm_block([r for r in cr if r["arm"] == arm]) for arm in AB.ARMS}
        valid_arms = [arm for arm in AB.ARMS if c["validity_19_of_20"][arm]]
        spec_best = min(valid_arms, key=lambda x: arms[x]["T_oracle_ms"]["median"])
        keep_best = c["E2"]["best_composed_arm"]
        per_arm = {}
        for arm in sorted({"K5V", "K5EV", spec_best, keep_best}):
            b = arms[arm]
            exc = AB.mean([r["first_snapshot_excess_ms"] for r in cr if r["arm"] == arm and r["valid"]]) or 0.0
            sub = b["sub_mean_ms"]
            untested = {"admission_residual_after_V": (sub.get("pre_admission_validate", 0.0) + sub.get("pre_inner_validate", 0.0))
                        if arm in AB.V_ARMS else 0.0,
                        "unattributed": b["components_mean_ms"]["unattributed"] or 0.0}
            if wv.startswith("UNDECIDED"):
                untested["first_snapshot_cold_excess"] = exc
            meanT = b["T_runner_ms"]["mean"]
            per_arm[arm] = {"T_oracle_median_ms": b["T_oracle_ms"]["median"], "T_runner_mean_ms": meanT,
                            "n_valid": b["valid"], "first_snapshot_excess_mean_ms": exc,
                            "first_snapshot_excess_median_ms": b["first_snapshot_excess_ms_median"],
                            "rows": verdict_rows(cls, arm, b, ev, vv, wv, exc),
                            "untested_ms": untested, "untested_share": sum(untested.values()) / meanT}
        out["classes"][cls] = {"verdicts": {"H_E": ev, "H_V": vv, "H_W": wv},
                               "T_oracle_median_ms": {arm: arms[arm]["T_oracle_ms"]["median"] for arm in AB.ARMS},
                               "best_spec_literal": spec_best, "best_b02_keep_only": keep_best, "arms": per_arm}
    out = json.loads(json.dumps(out, sort_keys=True, default=lambda x: round(x, 6) if isinstance(x, float) else str(x)))
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for cls, c in out["classes"].items():
        print(cls, "spec-best", c["best_spec_literal"], "keep-best", c["best_b02_keep_only"],
              {arm: round(v["untested_share"], 4) for arm, v in c["arms"].items()})


if __name__ == "__main__":
    main()
