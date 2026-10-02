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
W0_RATIONALE = (
    "W0 = alpha/2 = 0.025, the usual LORD++ choice. For ~30 tests a night with no rejection the levels run "
    "1.25e-3 (t=1), 2.3e-4 (t=3), 9.1e-5 (t=10), 3.2e-5 (t=30) and spend 0.0037 of the 0.025 wealth, so a night "
    "never exhausts it. A larger W0 (up to alpha) raises those levels at most 2x but shrinks the first "
    "rejection's reward (alpha - W0); after any rejection the later levels are nearly W0-independent "
    "(alpha_30 ~6.5e-5 for W0 in 0.01..0.049). G5's sign-flip p resolves alpha_i/20 at every level, so W0 decides "
    "only marginal effects: at n=37 and the loaded-host T_act sigma 0.0376, 80% power needs ~2.4% at t=1 and "
    "~3.0% at t=30."
)


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


def next_alpha(prior_p_values: Sequence[float]) -> float:
    """The level of the next test; it depends only on earlier rejections, never on its own p."""
    return replay([*prior_p_values, 1.0])[-1]["alpha_i"]


def decide(prior_p_values: Sequence[float], p_value: float) -> dict:
    """The decision for the next test after ``prior_p_values``."""
    return replay([*prior_p_values, p_value])[-1]
