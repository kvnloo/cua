"""Write summary.json (headline numbers + evidence class per row) from the committed raw/ analysis.

  python make_summary.py <packet_dir>
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROWS = ["base_rate_in_sample", "deterministic_constant_0_5", "deterministic_loo_group_prior", "laya_421m", "julia_1",
        "decider_2b", "nanojev", "qwen_3b_baseline", "failopen_ollama_deadport"]
EVIDENCE = {"deterministic_constant_0_5": "FIXTURE (arithmetic over REAL labels)", "deterministic_loo_group_prior": "FIXTURE (arithmetic over REAL labels)",
            "base_rate_in_sample": "FIXTURE (oracle-optimistic reference)", "failopen_ollama_deadport": "REAL (control)"}


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def main() -> None:
    packet = Path(sys.argv[1])
    raw = packet / "raw"
    runs = jl(packet / "dataset" / "runs.jsonl")
    ran = [r for r in runs if r["status"] == "RUN"]
    ledger = jl(raw / "quiet-lane-ledger.samples.jsonl")
    out = {"schema": "stack.samples.summary.v1",
           "dataset_content_sha256": json.loads((packet / "dataset" / "MANIFEST.json").read_text())["content_sha256"],
           "workload": {"tasks": len(runs), "run": len(ran), "not_run_deadline": len(runs) - len(ran),
                        "oracle_pass": sum(r.get("verified_success") is True for r in ran),
                        "oracle_fail": sum(r.get("verified_success") is False for r in ran),
                        "oracle_unknown": sum(r.get("verified_success") is None for r in ran),
                        "by_kind": {}, "by_family": {}, "exit_codes": {},
                        "wall_s_median": statistics.median([r["wall_s"] for r in ran]) if ran else None,
                        "timeouts": sum(bool(r.get("timed_out")) for r in ran),
                        "isolation_mask_ok_all": all(r["isolation"]["ok"] for r in ran),
                        "live_home_file_stats_unchanged_runs": sum(bool(r["isolation"]["live_home_stat_unchanged"]) for r in ran),
                        "live_home_changed_entries": sorted({json.dumps(c, sort_keys=True) for r in ran for c in r["isolation"]["live_home_changed_entries"]}),
                        "live_home_dir_mtime_moved_runs": sum(bool(r["isolation"]["live_home_dir_mtime_moved"]) for r in ran)},
           "lanes": {}, "timed_labels": sorted({l["label"] for l in ledger if l["label"].startswith("samples-score-")})}
    for r in ran:
        for key, val in (("by_kind", r["kind"]), ("by_family", r["family"])):
            d = out["workload"][key].setdefault(val, {"run": 0, "pass": 0, "fail": 0, "unknown": 0})
            d["run"] += 1
            d["pass" if r.get("verified_success") is True else "fail" if r.get("verified_success") is False else "unknown"] += 1
        out["workload"]["exit_codes"][str(r["exit_code"])] = out["workload"]["exit_codes"].get(str(r["exit_code"]), 0) + 1
    events = jl(packet / "dataset" / "events.jsonl")
    posts = [e for e in events if e.get("event") == "post_api_request"]
    trunc = sum(1 for e in posts if int((e.get("usage") or {}).get("prompt_tokens") or 0) >= 4096)
    out["workload"]["api_attempts_post"] = len(posts)
    out["workload"]["api_attempts_prompt_tokens_ge_4096"] = trunc
    out["workload"]["observer_rows_dropped"] = sum(int((e.get("fields") or {}).get("dropped_rows") or 0)
                                                   for e in events if e.get("event") == "observer_rows_dropped")
    for lane, file in (("api.attempt_will_fail", "api-analysis.json"), ("verification_needed", "turn-analysis.json")):
        a = json.loads((raw / "analysis" / file).read_text())
        rows = {}
        loo = a["rows"].get("deterministic_loo_group_prior", {})
        any_row = next((v for v in a["rows"].values() if v.get("n")), {})
        rows["base_rate_in_sample"] = {"brier": any_row.get("base_rate_brier"), "evidence": EVIDENCE["base_rate_in_sample"]}
        for name in ROWS[1:]:
            v = a["rows"].get(name)
            if v is None:
                rows[name] = {"evidence": "NOT_RUN"}
                continue
            rows[name] = {k: v.get(k) for k in ("n", "brier", "log_loss", "accuracy_at_0_5", "ece", "positive_rate",
                                                 "n_probability_exactly_0_or_1")}
            rows[name]["coverage"] = (v.get("denominators") or {}).get("coverage")
            rows[name]["denominators"] = v.get("denominators")
            rows[name]["vs_loo_prior"] = v.get("vs_deterministic_loo_group_prior")
            rows[name]["latency"] = v.get("latency")
            rows[name]["evidence"] = EVIDENCE.get(name, "REAL + BENCHMARK (quiet-lane timed scoring process)")
        rows["jev_reference"] = {"evidence": "NOT_RUN", "why": "TypeSafe, paid (policy)"}
        out["lanes"][lane] = {"n_examples": a["n_examples"], "n_labelled": a["n_labelled"], "n_positive": a["n_positive"],
                              "n_negative": a["n_negative"], "n_unknown_label": a["n_unknown_label"], "G2": a["G2"],
                              "rows": rows, "disagreement": a["disagreement"]}
    out["audits"] = {"api": json.loads((raw / "examples" / "api-audit.json").read_text()),
                     "turn": json.loads((raw / "examples" / "turn-audit.json").read_text())}
    (packet / "summary.json").write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: out["workload"][k] for k in ("run", "oracle_pass", "oracle_fail", "oracle_unknown")}))


if __name__ == "__main__":
    main()
