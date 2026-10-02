"""Write summary.json from the committed analysis, audits and frozen runs (no new computation of metrics).

  python make_summary.py <packet_dir>
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def main() -> None:
    P = Path(sys.argv[1])
    t = json.loads((P / "raw/analysis/turn-analysis.json").read_text())
    a = json.loads((P / "raw/analysis/api-analysis.json").read_text())
    runs = jl(P / "dataset/runs.jsonl")
    man = json.loads((P / "dataset/MANIFEST.json").read_text())
    run = [r for r in runs if r["status"] == "RUN"]
    fam = defaultdict(lambda: [0, 0, 0])
    for r in run:
        f = fam[r["family"]]
        f[0] += r["verified_success"] is True
        f[1] += r["verified_success"] is False
        f[2] += r["verified_success"] is None

    def rowsum(rows: dict) -> dict:
        out = {}
        for k, v in rows.items():
            if "error" in v:
                out[k] = {"error": v["error"]}
                continue
            out[k] = {"brier": v.get("brier"), "log_loss": v.get("log_loss"), "ece": v.get("ece"),
                      "accuracy_at_0_5": v.get("accuracy_at_0_5"), "denominators": v.get("denominators"),
                      "vs_reference_descriptive": v.get("vs_reference_descriptive"), "latency": v.get("latency"),
                      "backend_error_kinds": v.get("backend_error_kinds"),
                      "n_probability_exactly_0_or_1": v.get("n_probability_exactly_0_or_1")}
        return out

    summary = {
        "schema": "stack2.confirm.summary.v1",
        "dataset": {"content_sha256": man["content_sha256"], "counts": man["counts"], "frozen_at": man["frozen_at"]},
        "workload": {
            "run": len(run), "not_run": len(runs) - len(run),
            "oracle": dict(Counter("pass" if r["verified_success"] else "unknown" if r["verified_success"] is None else "fail" for r in run)),
            "by_kind": {k: dict(Counter("pass" if r["verified_success"] else "unknown" if r["verified_success"] is None else "fail"
                                        for r in run if r["kind"] == k)) for k in ("file", "cua")},
            "by_family": {k: {"pass": v[0], "fail": v[1], "unknown": v[2]} for k, v in sorted(fam.items())},
            "exit_codes": dict(Counter(str(r["exit_code"]) for r in run)),
            "harness_errors": sum(1 for r in run if r.get("harness_error")),
            "timeouts": sum(1 for r in run if r["timed_out"]),
            "wall_s_median_descriptive": statistics.median(r["wall_s"] for r in run) if run else None,
            "isolation_ok": sum(1 for r in run if r["isolation"]["ok"]),
        },
        "confirmatory": t["confirmatory_test"],
        "turn_lane": {"n_examples": t["n_examples"], "n_labelled": t["n_labelled"], "n_positive": t["n_positive"],
                      "n_negative": t["n_negative"], "n_unknown_label": t["n_unknown_label"], "G2": t["G2"],
                      "disagreement": t["disagreement"]},
        "turn_rows": rowsum(t["rows"]),
        "api_lane": {"n_examples": a["n_examples"], "n_labelled": a["n_labelled"], "n_positive": a["n_positive"],
                     "n_negative": a["n_negative"], "degenerate": a["G2"]["degenerate"], "G2": a["G2"]},
        "api_rows": rowsum(a["rows"]),
        "promotion_ready": False,
    }
    for name in ("turn-audit.json", "api-audit.json"):
        p = P / "raw/examples" / name
        if p.exists():
            summary[name.replace("-audit.json", "_audit")] = json.loads(p.read_text())
    (P / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verdict": t["confirmatory_test"]["verdict"], "api_degenerate": a["G2"]["degenerate"]}))


if __name__ == "__main__":
    main()
