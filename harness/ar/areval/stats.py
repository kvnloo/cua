"""Pure statistics for the autoresearch evaluator (stdlib only, deterministic given a seed).

Effect size: the paired log ratio d_k = ln(T_candidate,k / T_champion,k) of pair k; Delta is
the mean of d_k. Negative Delta = candidate faster. All CIs are percentile bootstrap CIs;
the one-sided p-value for G5 is a paired sign-flip test sized to the LORD++ level it faces.
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


SIGN_FLIP_MIN_RESAMPLES = 20000
SIGN_FLIP_PER_ALPHA = 20  # resamples per unit 1/alpha: the p floor 1/(b+1) is <= alpha/20


def sign_flip_resamples(alpha: float) -> int:
    """Resamples for a test run at level ``alpha``: at least 20/alpha (and 20,000), so the
    smallest attainable p, 1/(b+1), is at most alpha/20 at every LORD++ level."""
    return max(SIGN_FLIP_MIN_RESAMPLES, math.ceil(SIGN_FLIP_PER_ALPHA / alpha))


def sign_flip_p_less(xs: Sequence[float], b: int, seed: int) -> float:
    """One-sided paired sign-flip (randomisation) p for H0: no effect, against H1: mean < 0.

    Under H0 each pair's ln ratio is as likely to be +|d_k| as -|d_k| (the arm order within a
    pair is AB/BA-randomised and the binaries are exchangeable), so the null distribution of
    sum(d) is that of sum(s_k |d_k|) with independent fair signs s_k. Monte Carlo over b sign
    vectors: p = (1 + #{resampled sum <= observed sum}) / (b + 1), a valid p for any b, with
    resolution 1/(b+1). No normality assumption. Sums are read from 8-pair lookup tables.
    """
    n = len(xs)
    mags = [abs(x) for x in xs]
    tables = []
    for start in range(0, n, 8):
        part = mags[start:start + 8]
        table = [0.0] * (1 << len(part))
        for mask in range(1, len(table)):
            low = mask & -mask
            table[mask] = table[mask ^ low] + part[low.bit_length() - 1]
        tables.append(table)
    # A sign vector with flipped set F has sum = total - 2 * sum_F |d|, which is <= the observed
    # sum exactly when sum_F |d| >= sum of the negative d's (the observed vector itself counts).
    need = sum(m for x, m in zip(xs, mags) if x < 0) - 1e-12 * (sum(mags) + 1.0)
    rng = random.Random(seed)
    hits = 0
    for _ in range(b):
        bits = rng.getrandbits(n)
        flipped = 0.0
        for table in tables:
            flipped += table[bits & 0xFF]
            bits >>= 8
        if flipped >= need:
            hits += 1
    return (1 + hits) / (b + 1)


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
