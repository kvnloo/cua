"""Pure statistics for the autoresearch evaluator (stdlib only, deterministic given a seed).

Effect size: the paired log ratio d_k = ln(T_candidate,k / T_champion,k) of pair k; Delta is
the mean of d_k. Negative Delta = candidate faster. All CIs are percentile bootstrap CIs;
the one-sided p-value for H0: Delta >= 0 is a null-shifted bootstrap.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist, fmean, stdev
from typing import Sequence

TAU_FLOOR = 0.02
ALPHA_ONE_SIDED = 0.01
POWER = 0.80


def quantile(xs: Sequence[float], q: float) -> float:
    """Type-7 (linear interpolation) quantile, like numpy's default."""
    if not xs:
        raise ValueError("quantile of empty sequence")
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def ln_ratios(pairs: Sequence[tuple[float, float]]) -> list[float]:
    """(champion T, candidate T) pairs -> ln(candidate / champion)."""
    return [math.log(c / a) for a, c in pairs]


def bootstrap_means(xs: Sequence[float], b: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(xs)
    return [fmean(xs[rng.randrange(n)] for _ in range(n)) for _ in range(b)]


def bootstrap_ci(xs: Sequence[float], level: float = 0.95, b: int = 4000, seed: int = 1) -> tuple[float, float]:
    means = bootstrap_means(xs, b, seed)
    tail = (1 - level) / 2
    return quantile(means, tail), quantile(means, 1 - tail)


def bootstrap_p_less(xs: Sequence[float], b: int = 4000, seed: int = 2) -> float:
    """One-sided p for H0: mean >= 0 against H1: mean < 0 (null-shifted bootstrap)."""
    m = fmean(xs)
    shifted = [x - m for x in xs]
    means = bootstrap_means(shifted, b, seed)
    return (1 + sum(1 for mb in means if mb <= m)) / (b + 1)


def tau_from_aa(aa_d: Sequence[float], batch: int, b: int = 4000, seed: int = 3) -> dict[str, float]:
    """tau = max(2%, 97.5th percentile of |Delta_AA|) in relative units.

    Delta_AA is the mean ln ratio of an AA batch (champion vs champion) of ``batch`` pairs;
    its distribution is estimated by resampling batches from the calibration pairs.
    """
    rng = random.Random(seed)
    n = len(aa_d)
    abs_means = [abs(fmean(aa_d[rng.randrange(n)] for _ in range(batch))) for _ in range(b)]
    q = quantile(abs_means, 0.975)
    return {"q975_abs_delta_aa_ln": q, "tau": max(TAU_FLOOR, math.exp(q) - 1), "floor": TAU_FLOOR,
            "aa_pairs": n, "batch": batch}


def z_sum(alpha: float = ALPHA_ONE_SIDED, power: float = POWER) -> float:
    nd = NormalDist()
    return nd.inv_cdf(1 - alpha) + nd.inv_cdf(power)


def n_pairs_required(sigma: float, tau: float, alpha: float = ALPHA_ONE_SIDED, power: float = POWER) -> int:
    """n = (z_{1-alpha} + z_power)^2 (sigma / delta)^2 with delta = ln(1 + tau).

    (z_.99 + z_.80)^2 = 10.04, the "10 (sigma/delta)^2" of the plan; ln(1+tau) <= tau, so this
    is the conservative reading of "delta = tau".
    """
    delta = math.log1p(tau)
    return max(2, math.ceil(z_sum(alpha, power) ** 2 * (sigma / delta) ** 2))


def achieved_power(sigma: float, tau: float, n: int, alpha: float = ALPHA_ONE_SIDED) -> float:
    if sigma <= 0 or n < 2:
        return 1.0 if sigma <= 0 else 0.0
    nd = NormalDist()
    return nd.cdf(math.log1p(tau) * math.sqrt(n) / sigma - nd.inv_cdf(1 - alpha))


def sd(xs: Sequence[float]) -> float:
    return stdev(xs) if len(xs) >= 2 else 0.0
