"""Evaluate every preregistered row of one lane on exactly the same frozen examples.

  python analyze.py <hermes_worktree> <lane_id> <examples.jsonl> <scored_dir> <runs.jsonl> <output.json>

Rows: base_rate_in_sample (reference), deterministic_constant_0_5, deterministic_loo_group_prior and
every scored-<row>.jsonl in scored_dir. Metrics come from the exp/stack-samples evaluate_shadow.evaluate
(question-id aware, explicit denominators); this script adds ECE, latency, paired bootstrap vs the
deterministic prior, the G2 degeneracy gate and disagreement slices (PREREG.json metrics/gates).
"""
from __future__ import annotations

import importlib.util
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SEED = 20261002
BOOT = 2000


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def key(ex: dict) -> str:
    ident = ex.get("identity") or {}
    return json.dumps([ident.get("trace_id"), ident.get("api_request_id"), ex["request"].get("request_id"),
                       (ex["request"].get("state") or {}).get("api_call_count"), ident.get("work_item_id")])


def p_true(row: dict, qid: str) -> float | None:
    if row.get("backend_error"):
        return None
    for a in ((row.get("decision") or {}).get("answers") or []):
        if a.get("question_id") == qid:
            v = (a.get("probabilities") or {}).get("true")
            return float(v) if isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 else None
    return None


def synthetic(examples: list[dict], qid: str, fn, name: str) -> list[dict]:
    rows = []
    for i, ex in enumerate(examples):
        p = fn(i, ex)
        row = dict(ex)
        row["decision"] = {"backend": name, "latency_ms": 0.0, "answers": [
            {"question_id": qid, "probabilities": {"false": 1 - p, "true": p}, "value": p >= 0.5}]}
        rows.append(row)
    return rows


def binom_cdf(k: int, n: int, p: float) -> float:
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def cp_upper(k: int, n: int, alpha: float = 0.05) -> float:
    """Exact one-sided Clopper-Pearson upper bound on a binomial rate."""
    if n == 0:
        return 1.0
    if k >= n:
        return 1.0
    lo, hi = k / n, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if binom_cdf(k, n, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def main() -> None:
    hermes_wt, qid, ex_path, scored_dir, runs_path, out_path = (Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]),
                                                               Path(sys.argv[4]), Path(sys.argv[5]), Path(sys.argv[6]))
    spec = importlib.util.spec_from_file_location("evaluate_shadow", hermes_wt / "lab" / "z0_hermes_observer" / "evaluate_shadow.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    examples = read_jsonl(ex_path)
    runs = read_jsonl(runs_path)
    by_session = {r.get("session_id"): r for r in runs if r.get("session_id")}

    def slice_of(ex: dict) -> dict:
        if ex.get("slice"):
            return ex["slice"]
        run = by_session.get((ex.get("identity") or {}).get("session_id"), {})
        return {"kind": run.get("kind"), "family": run.get("family")}

    def group_of(ex: dict) -> str:
        if qid == "verification_needed":
            return slice_of(ex).get("family") or "?"
        return (ex.get("identity") or {}).get("session_id") or "?"

    labelled = [(i, ex) for i, ex in enumerate(examples) if isinstance(ex.get("verified_outcome"), bool)]
    pos = sum(ex["verified_outcome"] for _, ex in labelled)
    n_lab = len(labelled)
    totals = defaultdict(lambda: [0, 0])
    for _, ex in labelled:
        g = totals[group_of(ex)]
        g[0] += int(ex["verified_outcome"])
        g[1] += 1

    def loo(i: int, ex: dict) -> float:
        g = totals.get(group_of(ex), [0, 0])
        own_pos, own_n = (g if isinstance(ex.get("verified_outcome"), bool) else (0, 0))
        return (pos - own_pos + 0.5) / (n_lab - own_n + 1)

    rows: dict[str, list[dict]] = {
        "deterministic_constant_0_5": synthetic(examples, qid, lambda i, ex: 0.5, "deterministic_constant_0_5"),
        "deterministic_loo_group_prior": synthetic(examples, qid, loo, "deterministic_loo_group_prior"),
    }
    for path in sorted(scored_dir.glob("scored-*.jsonl")):
        rows[path.stem.removeprefix("scored-")] = read_jsonl(path)

    ex_keys = [key(ex) for ex in examples]
    report = {"schema": "stack.samples.lane_analysis.v1", "question_id": qid, "n_examples": len(examples),
              "n_labelled": n_lab, "n_positive": pos, "n_negative": n_lab - pos,
              "n_unknown_label": len(examples) - n_lab}
    minority = min(pos, n_lab - pos)
    report["G2"] = {"degenerate": pos < 5 or (n_lab - pos) < 5,
                    "positive_rate": (pos / n_lab) if n_lab else None,
                    "minority_rate_upper95_clopper_pearson": cp_upper(minority, n_lab) if n_lab else None,
                    "positive_rate_upper95_clopper_pearson": cp_upper(pos, n_lab) if n_lab else None}
    ref = {key(r): p_true(r, qid) for r in rows["deterministic_loo_group_prior"]}
    labels = {key(ex): ex.get("verified_outcome") for ex in examples}
    groups = {key(ex): group_of(ex) if qid != "verification_needed" else key(ex) for ex in examples}
    slices = {key(ex): slice_of(ex) for ex in examples}
    rng = random.Random(SEED)
    per_row = {}
    probs_by_row: dict[str, dict[str, float]] = {}
    for name, scored in rows.items():
        if [key(r) for r in scored] != ex_keys:
            per_row[name] = {"error": "scored rows do not match the frozen examples one-to-one"}
            continue
        base = ev.evaluate(scored, question_id=qid)
        bins = base.get("calibration_bins") or []
        n = base.get("n") or 0
        base["ece"] = (sum(b["n"] * abs(b["mean_probability"] - b["observed_rate"]) for b in bins) / n) if n else None
        probs = {key(r): p for r in scored if (p := p_true(r, qid)) is not None}
        probs_by_row[name] = probs
        base["n_probability_exactly_0_or_1"] = sum(1 for p in probs.values() if p in (0.0, 1.0))
        # latency (scorer timing is absent on synthetic rows)
        timing = [r.get("scorer_timing") or {} for r in scored]
        walls = [t["wall_ms"] for t in timing if "wall_ms" in t]
        reported = [float((r.get("decision") or {}).get("latency_ms")) for r in scored
                    if isinstance((r.get("decision") or {}).get("latency_ms"), (int, float)) and r.get("scorer_timing")]
        if timing and timing[0].get("backend_create_ms") is not None:
            base["latency"] = {"backend_create_ms": timing[0]["backend_create_ms"],
                               "first_call_wall_ms": walls[0] if walls else None,
                               "warm_wall_ms_p50": pct(walls[1:], 0.5), "warm_wall_ms_p95": pct(walls[1:], 0.95),
                               "warm_reported_latency_ms_p50": pct(reported[1:], 0.5),
                               "warm_reported_latency_ms_p95": pct(reported[1:], 0.95), "n_calls": len(walls)}
        # paired bootstrap of Brier(row) - Brier(loo prior) over examples with a label and both probabilities
        common = [k for k in ex_keys if isinstance(labels[k], bool) and k in probs and ref.get(k) is not None]
        if name != "deterministic_loo_group_prior" and common:
            gmap = defaultdict(list)
            for k in common:
                gmap[groups[k]].append(k)
            gl = list(gmap)
            diff = lambda ks: statistics.fmean([(probs[k] - labels[k]) ** 2 - (ref[k] - labels[k]) ** 2 for k in ks])  # noqa: E731
            point = diff(common)
            boots = []
            for _ in range(BOOT):
                ks = [k for g in (rng.choice(gl) for _ in gl) for k in gmap[g]]
                boots.append(diff(ks))
            lo, hi = pct(boots, 0.025), pct(boots, 0.975)
            base["vs_deterministic_loo_group_prior"] = {
                "n_common": len(common), "brier_diff": point, "ci95": [lo, hi],
                "G3": "beats" if hi < 0 else ("worse" if lo > 0 else "no_detectable_difference")}
        # slices
        sl = defaultdict(list)
        for k in common or [k for k in ex_keys if isinstance(labels[k], bool) and k in probs]:
            s = slices[k]
            sl[f"kind={s.get('kind')}"].append((probs[k] - labels[k]) ** 2)
            if qid == "verification_needed":
                sl[f"family={s.get('family')}"].append((probs[k] - labels[k]) ** 2)
        base["brier_slices"] = {s: {"n": len(v), "brier": statistics.fmean(v)} for s, v in sorted(sl.items())}
        per_row[name] = base
    report["rows"] = per_row
    model_rows = [r for r in probs_by_row if not r.startswith("deterministic") and not r.startswith("failopen")]
    dis = {}
    for i, a in enumerate(model_rows):
        for b in model_rows[i + 1:]:
            ks = [k for k in probs_by_row[a] if k in probs_by_row[b]]
            if ks:
                dis[f"{a}|{b}"] = {"n": len(ks), "disagree_rate_at_0_5":
                                   sum((probs_by_row[a][k] >= 0.5) != (probs_by_row[b][k] >= 0.5) for k in ks) / len(ks)}
    full = [k for k in ex_keys if isinstance(labels[k], bool) and all(k in probs_by_row[r] for r in model_rows)]
    report["disagreement"] = {
        "pairwise": dis,
        "n_labelled_scored_by_all_model_rows": len(full),
        "all_model_rows_wrong": sum(all((probs_by_row[r][k] >= 0.5) != labels[k] for r in model_rows) for k in full),
        "all_model_rows_right": sum(all((probs_by_row[r][k] >= 0.5) == labels[k] for r in model_rows) for k in full),
        "model_rows": model_rows,
    }
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"lane": qid, "n_labelled": n_lab, "positives": pos, "degenerate": report["G2"]["degenerate"],
                      "rows": {k: (v.get("brier"), v.get("denominators", {}).get("coverage")) for k, v in per_row.items()}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
