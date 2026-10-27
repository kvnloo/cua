#!/usr/bin/env python3
"""Summarize cua.h2h.attempt.v1 receipts: per tool x mode x effect cell and paired block deltas.

Input: the raw JSONL produced from the shards (warm-up attempts are kept in the raw file and
excluded here). Every non-warm-up attempt counts; failures count against the tool.
Latency percentiles use the nearest-rank method over verified attempts only, and the success
rate is over all attempts. Paired delta = per block, mean(CUA) - mean(opencli); the median of
those deltas has a seeded bootstrap 95% interval (2000 resamples).
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def pct(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def boot_median_ci(values: list[float], seed: int = 20261027, n: int = 2000) -> tuple[float, float]:
    rng = random.Random(seed)
    meds = sorted(statistics.median(rng.choices(values, k=len(values))) for _ in range(n))
    return meds[int(0.025 * n)], meds[int(0.975 * n) - 1]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("attempts", type=Path)
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    rows = [json.loads(line) for line in a.attempts.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if not r.get("warmup")]
    cells = defaultdict(list)
    blocks = defaultdict(lambda: defaultdict(list))
    for r in rows:
        cells[(r["tool"], r["mode"], r["effect"])].append(r)
        blocks[(r["mode"], r["effect"])][r["block_id"]].append(r)
    out = {"cells": [], "paired": [], "safety": {}}
    for key in sorted(cells):
        rs = cells[key]
        ok = [r["elapsed_ms"] for r in rs if r.get("oracle_outcome") == "verified"]
        out["cells"].append({
            "tool": key[0], "mode": key[1], "effect": key[2], "n": len(rs),
            "verified": len(ok), "success_rate": round(len(ok) / len(rs), 4),
            "median_ms": round(statistics.median(ok), 1) if ok else None,
            "p90_ms": round(pct(ok, 0.90), 1) if ok else None,
            "p95_ms": round(pct(ok, 0.95), 1) if ok else None,
            "outcomes": dict(sorted(Counter(str(r.get("oracle_outcome")) for r in rs).items())),
        })
    for key in sorted(blocks):
        deltas, complete = [], 0
        for bid, rs in blocks[key].items():
            a_ms = [r["elapsed_ms"] for r in rs if r["tool"] == "cua" and r.get("oracle_outcome") == "verified"]
            b_ms = [r["elapsed_ms"] for r in rs if r["tool"] == "opencli" and r.get("oracle_outcome") == "verified"]
            if len(rs) == 4 and len(a_ms) == 2 and len(b_ms) == 2:
                complete += 1
                deltas.append(statistics.mean(a_ms) - statistics.mean(b_ms))
        if deltas:
            lo, hi = boot_median_ci(deltas)
            out["paired"].append({"mode": key[0], "effect": key[1], "blocks": len(blocks[key]),
                                  "complete_verified_blocks": complete,
                                  "median_delta_cua_minus_opencli_ms": round(statistics.median(deltas), 1),
                                  "ci95_ms": [round(lo, 1), round(hi, 1)],
                                  "cua_faster_blocks": sum(d < 0 for d in deltas)})
    for flag in ("unauthorized_effect", "duplicate_effect", "wrong_target", "uncertain_effect"):
        out["safety"][flag] = sum(1 for r in rows if r.get(flag))
    out["safety"]["fallbacks"] = sum(r.get("fallback_count", 0) for r in rows)
    out["safety"]["model_calls"] = sum(r.get("model_calls", 0) for r in rows)
    text = json.dumps(out, indent=1, sort_keys=True)
    if a.out:
        a.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
