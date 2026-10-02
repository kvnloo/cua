"""Summarise bench/raw/<backend>.json files plus quiet-lane ledger lines into bench/bench_summary.json.

usage: bench_summarize.py <bench dir> <quiet ledger excerpt jsonl> <backend[:EVIDENCE[:note]]> ...
"""
import json
import statistics
import sys
from pathlib import Path


def pct(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


bench = Path(sys.argv[1])
ledger = [json.loads(x) for x in Path(sys.argv[2]).read_text().splitlines() if x.strip()]
out = {"schema": "stack_smoke.bench_summary.v1", "backends": {}}
for spec in sys.argv[3:]:
    name, ev, note = (spec.split(":", 2) + ["", ""])[:3]
    p = bench / "raw" / f"{name}.json"
    if ev != "BENCHMARK" or not p.exists():
        out["backends"][name] = {"evidence": ev or "NOT_RUN", "note": note}
        continue
    d = json.loads(p.read_text())
    rows = d["rows"]
    warm = [r["latency_ms"] for r in rows[1:] if r["status"] == "ok"]
    wall = [r["wall_ms"] for r in rows[1:] if r["status"] == "ok"]
    out["backends"][name] = {
        "evidence": "BENCHMARK", "note": note, "n_requests": len(rows),
        "errors": sum(r["status"] != "ok" for r in rows),
        "cold_ms": rows[0].get("cold_ms_from_process_start") if rows else None,
        "cold_first_call_backend_latency_ms": rows[0].get("latency_ms") if rows else None,
        "cold_first_call_wall_ms": rows[0].get("wall_ms") if rows else None,
        "warm_n": len(warm),
        "warm_latency_ms_p50": statistics.median(warm) if warm else None,
        "warm_latency_ms_p90": pct(warm, 0.9), "warm_latency_ms_max": max(warm) if warm else None,
        "warm_wall_ms_p50": statistics.median(wall) if wall else None,
        "backend": rows[0].get("backend") if rows else None, "model": rows[0].get("model") if rows else None,
        "revision": rows[0].get("revision") if rows else None,
        "loadavg_before": d["meta"].get("loadavg_before"), "loadavg_after": d["meta"].get("loadavg_after"),
        "gpu_mem_before": d["meta"].get("gpu_mem_before"), "gpu_mem_after": d["meta"].get("gpu_mem_after"),
        "quiet_lane": [x for x in ledger if x.get("label") == f"stack-smoke-h5-{name}"],
    }
(bench / "bench_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
print(json.dumps({k: {kk: v.get(kk) for kk in ("evidence", "cold_ms", "warm_latency_ms_p50", "warm_n", "errors")}
                  for k, v in out["backends"].items()}, indent=1))
