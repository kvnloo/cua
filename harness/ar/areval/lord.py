"""LORD++ online FDR control (Ramdas, Yang, Wainwright, Jordan 2017; Javanmard and Montanari 2018).

Test t (1-based) is run at level

    alpha_t = gamma_t W0 + (alpha - W0) gamma_{t - tau_1} + alpha * sum_{j >= 2} gamma_{t - tau_j}

where tau_j < t are the times of earlier rejections and gamma is the fixed, non-increasing
sequence gamma_j = C log(max(j, 2)) / (j exp(sqrt(log j))) with C = 0.0722 (sum <= 1).
Wealth after test t: W0 - sum_{i <= t} alpha_i + (alpha - W0) for the first rejection + alpha
for each later one. The only state is the ordered list of past p-values, reconstructed from
results.jsonl, so the procedure keeps no separate store.

A test index is consumed only when gate G5 is evaluated (a candidate rejected at G0-G4 never
tests its latency hypothesis).
"""

from __future__ import annotations

import math
from typing import Sequence

ALPHA = 0.05
W0 = ALPHA / 2
GAMMA_C = 0.0722


def gamma(j: int) -> float:
    if j < 1:
        return 0.0
    return GAMMA_C * math.log(max(j, 2)) / (j * math.exp(math.sqrt(math.log(j))))


def replay(p_values: Sequence[float], alpha: float = ALPHA, w0: float = W0) -> list[dict]:
    """Every test's index, level, decision and wealth, recomputed from the p-values alone."""
    out: list[dict] = []
    rejections: list[int] = []
    wealth = w0
    for i, p in enumerate(p_values):
        t = i + 1
        a = gamma(t) * w0
        if rejections:
            a += (alpha - w0) * gamma(t - rejections[0])
            a += alpha * sum(gamma(t - r) for r in rejections[1:])
        rejected = p <= a
        before = wealth
        wealth = wealth - a + ((alpha - w0 if not rejections else alpha) if rejected else 0.0)
        if rejected:
            rejections.append(t)
        out.append({"index": t, "alpha_i": a, "p_value": p, "rejected": rejected,
                    "wealth_before": before, "wealth_after": wealth, "alpha": alpha, "w0": w0})
    return out


def decide(prior_p_values: Sequence[float], p_value: float) -> dict:
    """The decision for the next test after ``prior_p_values``."""
    return replay([*prior_p_values, p_value])[-1]
