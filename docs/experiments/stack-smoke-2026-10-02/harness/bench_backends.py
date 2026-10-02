"""Cold/warm latency of one z0int shadow backend over a frozen set of real shadow requests.

usage (always under quiet-timed + hostless, one process per backend):
  STACK_T0=$(date +%s.%N) python bench_backends.py --backend <id> --requests frozen_requests.jsonl --out <file>
cold = STACK_T0 (shell time just before the interpreter starts) -> first answer; it includes interpreter start,
imports, model load and the first evaluate. warm = every following request, one pass, in file order.
Every failure is a row (status error) and stays in the denominators.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def gpu_mem() -> str | None:
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend", required=True)
    p.add_argument("--requests", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--z0-wt", required=True)
    a = p.parse_args()
    t0 = float(os.environ.get("STACK_T0") or time.time())
    sys.path[:0] = [a.z0_wt, str(Path(a.z0_wt) / "src")]
    reqs = [json.loads(line) for line in open(a.requests) if line.strip()]
    rows, meta = [], {"backend_arg": a.backend, "n_requests": len(reqs), "loadavg_before": os.getloadavg(),
                      "gpu_mem_before": gpu_mem()}
    from z0int.backends.base import request_from_mapping, result_to_dict
    from z0int.backends.registry import create_backend
    try:
        backend = create_backend(a.backend)
    except Exception as e:
        meta["create_error"] = f"{type(e).__name__}: {e}"
        backend = None
    for i, r in enumerate(reqs):
        s = time.perf_counter()
        wall_start = time.time()
        row = {"i": i, "question_id": r["questions"][0]["id"], "state_hash": r.get("_state_hash")}
        try:
            if backend is None:
                raise RuntimeError(meta.get("create_error", "no backend"))
            d = result_to_dict(backend.evaluate(request_from_mapping({k: v for k, v in r.items() if not k.startswith("_")})))
            row.update(status="ok", latency_ms=d.get("latency_ms"), backend=d.get("backend"), model=d.get("model"),
                       revision=d.get("revision"), probabilities=(d.get("answers") or [{}])[0].get("probabilities"))
        except Exception as e:
            row.update(status="error", error=f"{type(e).__name__}: {str(e)[:300]}")
        row["wall_ms"] = (time.perf_counter() - s) * 1000.0
        if i == 0:
            row["cold_ms_from_process_start"] = (time.time() - t0) * 1000.0
            row["first_call_started_after_process_start_ms"] = (wall_start - t0) * 1000.0
        rows.append(row)
    meta.update(loadavg_after=os.getloadavg(), gpu_mem_after=gpu_mem(), finished=time.time())
    Path(a.out).write_text(json.dumps({"meta": meta, "rows": rows}, indent=1) + "\n")
    ok = [x for x in rows[1:] if x["status"] == "ok"]
    print(json.dumps({"backend": a.backend, "n": len(rows), "ok": sum(x["status"] == "ok" for x in rows),
                      "cold_ms": rows[0].get("cold_ms_from_process_start") if rows else None, "warm_ok": len(ok)}))


if __name__ == "__main__":
    main()
