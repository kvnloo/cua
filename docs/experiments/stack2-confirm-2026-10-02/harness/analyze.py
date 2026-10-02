"""Evaluate every preregistered row of one lane on exactly the same frozen examples, and (verification_needed only)
run the preregistered confirmatory test of julia_1 against the deterministic LOO-family prior.

  python analyze.py <hermes_worktree> <lane_id> <examples.jsonl> <scored_dir> <output.json>

Adapted from the SAMPLES analyze.py. Rows: base_rate_in_sample (reference only), deterministic_constant_0_5,
deterministic_samples_prior (57/105), deterministic_loo_group_prior (THE reference) and every scored-<row>.jsonl in
scored_dir (scored-failopen_* rows are controls: reported, never compared). Metrics come from the exp/stack-confirm
evaluate_shadow.evaluate (question-id aware, explicit denominators); this script adds ECE, log-loss differences,
latency, descriptive bootstrap CIs, the G2 degeneracy gate, slices, disagreement and the confirmatory test
(PREREG.json confirmatory_test, descriptive_analysis, gates).
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

DESC_SEED, DESC_BOOT = 20261002, 2000          # descriptive CIs (as SAMPLES)
CONF_SEED, CONF_BOOT = 20261012, 10000         # confirmatory test
EPS = 1e-12
REFERENCE = "deterministic_loo_group_prior"
CONFIRM_ROW = "julia_1"
SAMPLES_PRIOR = 57 / 105


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def key(ex: dict) -> str:
    ident = ex.get("identity") or {}
    return json.dumps([ident.get("trace_id"), ident.get("api_request_id"), ex["request"].get("request_id"),
                       (ex["request"].get("state") or {}).get("api_call_count"),
                       (ex["request"].get("state") or {}).get("retry_count"), ident.get("work_item_id")])


def p_true(row: dict, qid: str) -> float | None:
    if row.get("backend_error"):
        return None
    for a in ((row.get("decision") or {}).get("answers") or []):
        if a.get("question_id") == qid:
            v = (a.get("probabilities") or {}).get("true")
            return float(v) if isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 else None
    return None


def ll(p: float, y: int) -> float:
    p = min(max(p, EPS), 1 - EPS)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


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
    if n == 0 or k >= n:
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


def ece_from(pairs: list[tuple[float, int]], nbins: int) -> tuple[float | None, list[dict]]:
    if not pairs:
        return None, []
    bins = []
    for b in range(nbins):
        lo, hi = b / nbins, (b + 1) / nbins
        bucket = [(p, y) for p, y in pairs if lo <= p < hi or (b == nbins - 1 and p == 1.0)]
        if bucket:
            bins.append({"lo": lo, "hi": hi, "n": len(bucket), "mean_probability": statistics.fmean(p for p, _ in bucket),
                         "observed_rate": statistics.fmean(y for _, y in bucket)})
    ece = sum(b["n"] * abs(b["mean_probability"] - b["observed_rate"]) for b in bins) / len(pairs)
    return ece, bins


def confirmatory(keys: list[str], labels: dict, pj: dict, pr: dict) -> dict:
    """PREREG confirmatory_test, verbatim: paired iid bootstrap over labelled examples, one-sided 95% bounds."""
    lab = [k for k in keys if isinstance(labels[k], bool)]
    n = len(lab)
    pos = sum(labels[k] for k in lab)
    missing = [k for k in lab if pj.get(k) is None]
    coverage = (n - len(missing)) / n if n else 0.0
    pre = {"n_labelled": n, "n_positive": pos, "n_negative": n - pos, "julia_missing_imputed_0_5": len(missing),
           "julia_coverage": coverage}
    ok = n >= 100 and pos >= 10 and (n - pos) >= 10 and coverage >= 0.9
    out = {"preconditions": dict(pre, met=ok), "B": CONF_BOOT, "seed": CONF_SEED}
    if not ok:
        out["verdict"] = "INCONCLUSIVE"
        return out

    def run(ks: list[str], imputed: bool, rng: random.Random) -> dict:
        res = {}
        pjv = {k: (pj[k] if pj.get(k) is not None else 0.5) for k in ks} if imputed else {k: pj[k] for k in ks}
        y = {k: int(labels[k]) for k in ks}
        diffs = {"brier": [(pjv[k] - y[k]) ** 2 - (pr[k] - y[k]) ** 2 for k in ks],
                 "log_loss": [ll(pjv[k], y[k]) - ll(pr[k], y[k]) for k in ks]}
        m = len(ks)
        for metric in ("brier", "log_loss"):  # Brier first, then log-loss, one seeded stream
            d = diffs[metric]
            point = statistics.fmean(d)
            boots = []
            for _ in range(CONF_BOOT):
                boots.append(sum(d[rng.randrange(m)] for _ in range(m)) / m)
            upper = pct(boots, 0.95)
            res[metric] = {"n": m, "julia_1": statistics.fmean((pjv[k] - y[k]) ** 2 for k in ks) if metric == "brier"
                           else statistics.fmean(ll(pjv[k], y[k]) for k in ks),
                           "reference": statistics.fmean((pr[k] - y[k]) ** 2 for k in ks) if metric == "brier"
                           else statistics.fmean(ll(pr[k], y[k]) for k in ks),
                           "mean_diff": point, "one_sided_upper95": upper,
                           "p_boot": (1 + sum(b >= 0 for b in boots)) / (CONF_BOOT + 1),
                           "reject_h0": upper < 0}
        return res

    primary = run(lab, True, random.Random(CONF_SEED))
    rb, rl = primary["brier"]["reject_h0"], primary["log_loss"]["reject_h0"]
    out["primary"] = primary
    out["verdict"] = ("CONFIRMED" if rb and rl else "BRIER_ONLY" if rb else "LOGLOSS_ONLY" if rl else "NOT_CONFIRMED")
    cc = [k for k in lab if pj.get(k) is not None]
    out["sensitivity_complete_case"] = run(cc, False, random.Random(CONF_SEED)) if len(cc) != n else "identical (no missing julia_1 probability)"
    return out


def main() -> None:
    hermes_wt, qid, ex_path, scored_dir, out_path = (Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]),
                                                     Path(sys.argv[4]), Path(sys.argv[5]))
    spec = importlib.util.spec_from_file_location("evaluate_shadow", hermes_wt / "lab" / "z0_hermes_observer" / "evaluate_shadow.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    examples = read_jsonl(ex_path)
    turn = qid == "verification_needed"

    def slice_of(ex: dict) -> dict:
        return ex.get("slice") or {}

    def group_of(ex: dict) -> str:
        return (slice_of(ex).get("family") or "?") if turn else ((ex.get("identity") or {}).get("session_id") or "?")

    labelled = [ex for ex in examples if isinstance(ex.get("verified_outcome"), bool)]
    pos = sum(ex["verified_outcome"] for ex in labelled)
    n_lab = len(labelled)
    totals = defaultdict(lambda: [0, 0])
    for ex in labelled:
        g = totals[group_of(ex)]
        g[0] += int(ex["verified_outcome"])
        g[1] += 1

    def loo(i: int, ex: dict) -> float:
        g = totals.get(group_of(ex), [0, 0])
        own_pos, own_n = (g if isinstance(ex.get("verified_outcome"), bool) else (0, 0))
        return (pos - own_pos + 0.5) / (n_lab - own_n + 1)

    rows: dict[str, list[dict]] = {
        "deterministic_constant_0_5": synthetic(examples, qid, lambda i, ex: 0.5, "deterministic_constant_0_5"),
        REFERENCE: synthetic(examples, qid, loo, REFERENCE),
    }
    if turn:
        rows["deterministic_samples_prior"] = synthetic(examples, qid, lambda i, ex: SAMPLES_PRIOR, "deterministic_samples_prior")
    for path in sorted(scored_dir.glob("scored-*.jsonl")):
        rows[path.stem.removeprefix("scored-")] = read_jsonl(path)

    ex_keys = [key(ex) for ex in examples]
    if len(set(ex_keys)) != len(ex_keys):
        raise SystemExit("example keys are not unique")
    report = {"schema": "stack2.confirm.lane_analysis.v1", "question_id": qid, "n_examples": len(examples),
              "n_labelled": n_lab, "n_positive": pos, "n_negative": n_lab - pos,
              "n_unknown_label": len(examples) - n_lab}
    minority = min(pos, n_lab - pos)
    report["G2"] = {"degenerate": pos < 5 or (n_lab - pos) < 5,
                    "positive_rate": (pos / n_lab) if n_lab else None,
                    "minority_rate_upper95_clopper_pearson": cp_upper(minority, n_lab) if n_lab else None,
                    "positive_rate_upper95_clopper_pearson": cp_upper(pos, n_lab) if n_lab else None}
    ref = {key(r): p_true(r, qid) for r in rows[REFERENCE]}
    labels = {key(ex): ex.get("verified_outcome") for ex in examples}
    groups = {key(ex): (key(ex) if turn else group_of(ex)) for ex in examples}
    slices = {key(ex): slice_of(ex) for ex in examples}
    rng = random.Random(DESC_SEED)
    per_row: dict[str, dict] = {}
    probs_by_row: dict[str, dict[str, float]] = {}
    for name, scored in rows.items():
        if [key(r) for r in scored] != ex_keys:
            per_row[name] = {"error": "scored rows do not match the frozen examples one-to-one"}
            continue
        base = ev.evaluate(scored, question_id=qid)
        probs = {key(r): p for r in scored if (p := p_true(r, qid)) is not None}
        probs_by_row[name] = probs
        pairs = [(probs[k], int(labels[k])) for k in ex_keys if isinstance(labels[k], bool) and k in probs]
        base["ece"], _ = ece_from(pairs, 5)
        if name == CONFIRM_ROW:
            base["ece_10bin"], base["calibration_bins_10"] = ece_from(pairs, 10)
        base["n_probability_exactly_0_or_1"] = sum(1 for p in probs.values() if p in (0.0, 1.0))
        errs = defaultdict(int)
        for r in scored:
            if r.get("backend_error"):
                be = r["backend_error"]
                errs[f"{be.get('stage')}:{be.get('type')}" if isinstance(be, dict) else str(be)[:80]] += 1
        base["backend_error_kinds"] = dict(errs)
        timing = [r.get("scorer_timing") or {} for r in scored]
        walls = [t["wall_ms"] for t in timing if "wall_ms" in t]
        reported = [float((r.get("decision") or {}).get("latency_ms")) for r in scored
                    if isinstance((r.get("decision") or {}).get("latency_ms"), (int, float)) and r.get("scorer_timing")]
        if timing and timing[0].get("backend_create_ms") is not None:
            base["latency"] = {"backend_create_ms": timing[0]["backend_create_ms"],
                               "first_call_wall_ms": walls[0] if walls else None,
                               "cold_total_ms": (timing[0]["backend_create_ms"] + walls[0]) if walls else None,
                               "warm_wall_ms_p50": pct(walls[1:], 0.5), "warm_wall_ms_p95": pct(walls[1:], 0.95),
                               "warm_wall_ms_max": max(walls[1:]) if len(walls) > 1 else None,
                               "warm_reported_latency_ms_p50": pct(reported[1:], 0.5),
                               "warm_reported_latency_ms_p95": pct(reported[1:], 0.95),
                               "warm_reported_latency_ms_max": max(reported[1:]) if len(reported) > 1 else None,
                               "n_calls": len(walls)}
        common = [k for k in ex_keys if isinstance(labels[k], bool) and k in probs and ref.get(k) is not None]
        if name != REFERENCE and not name.startswith("failopen") and common:
            gmap = defaultdict(list)
            for k in common:
                gmap[groups[k]].append(k)
            gl = list(gmap)
            fb = lambda ks: statistics.fmean([(probs[k] - labels[k]) ** 2 - (ref[k] - labels[k]) ** 2 for k in ks])  # noqa: E731
            fl = lambda ks: statistics.fmean([ll(probs[k], int(labels[k])) - ll(ref[k], int(labels[k])) for k in ks])  # noqa: E731
            bb, bl = [], []
            for _ in range(DESC_BOOT):
                ks = [k for g in (rng.choice(gl) for _ in gl) for k in gmap[g]]
                bb.append(fb(ks))
                bl.append(fl(ks))
            base["vs_reference_descriptive"] = {
                "n_common": len(common),
                "brier_diff": fb(common), "brier_ci95": [pct(bb, 0.025), pct(bb, 0.975)],
                "log_loss_diff": fl(common), "log_loss_ci95": [pct(bl, 0.025), pct(bl, 0.975)],
                "note": "two-sided descriptive interval; no claim"}
        sl = defaultdict(list)
        for k in [k for k in ex_keys if isinstance(labels[k], bool) and k in probs]:
            s = slices[k]
            y = int(labels[k])
            item = ((probs[k] - y) ** 2, ll(probs[k], y), y)
            sl[f"kind={s.get('kind')}"].append(item)
            if turn:
                sl[f"app={s.get('app')}"].append(item)
                sl[f"family={s.get('family')}"].append(item)
                sl[f"execution_completed={s.get('execution_completed')}"].append(item)
        base["slices"] = {s: {"n": len(v), "positives": sum(i[2] for i in v), "brier": statistics.fmean(i[0] for i in v),
                              "log_loss": statistics.fmean(i[1] for i in v)} for s, v in sorted(sl.items())}
        per_row[name] = base
    report["rows"] = per_row
    model_rows = [r for r in probs_by_row if not r.startswith("deterministic") and not r.startswith("failopen")]
    dis = {}
    for i, a in enumerate(model_rows + [REFERENCE]):
        for b in (model_rows + [REFERENCE])[i + 1:]:
            ks = [k for k in probs_by_row[a] if k in probs_by_row[b]]
            if ks:
                dis[f"{a}|{b}"] = {"n": len(ks), "disagree_rate_at_0_5":
                                   sum((probs_by_row[a][k] >= 0.5) != (probs_by_row[b][k] >= 0.5) for k in ks) / len(ks)}
    full = [k for k in ex_keys if isinstance(labels[k], bool) and all(k in probs_by_row[r] for r in model_rows)]
    report["disagreement"] = {
        "pairwise": dis, "model_rows": model_rows,
        "n_labelled_scored_by_all_model_rows": len(full),
        "all_model_rows_wrong": sum(all((probs_by_row[r][k] >= 0.5) != labels[k] for r in model_rows) for k in full),
        "all_model_rows_right": sum(all((probs_by_row[r][k] >= 0.5) == labels[k] for r in model_rows) for k in full),
        "all_model_rows_wrong_by_family": dict(sorted(
            {f: sum(1 for k in full if slices[k].get("family") == f
                    and all((probs_by_row[r][k] >= 0.5) != labels[k] for r in model_rows))
             for f in {slices[k].get("family") for k in full}}.items(), key=lambda x: str(x[0]))) if turn else None,
    }
    if turn:
        pj = {k: probs_by_row.get(CONFIRM_ROW, {}).get(k) for k in ex_keys}
        report["confirmatory_test"] = (confirmatory(ex_keys, labels, pj, ref) if CONFIRM_ROW in probs_by_row
                                       else {"verdict": "INCONCLUSIVE", "reason": "julia_1 row missing"})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"lane": qid, "n_labelled": n_lab, "positives": pos, "degenerate": report["G2"]["degenerate"],
                      "confirmatory": (report.get("confirmatory_test") or {}).get("verdict")}, sort_keys=True))


if __name__ == "__main__":
    main()
