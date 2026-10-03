"""R2-07e analysis (pre-registered gate statistic; the full analysis is completed after the PREREG commit).

paired_gate: median paired difference with a seeded paired percentile bootstrap CI at LEVEL
(two-sided 97.5%, seed 20261003, 10 000 resamples). Same resampling scheme as
b01_analysis.boot_ci (index resampling with replacement, sorted, floor/ceil percentile indices);
only the seed and the level differ.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Any

SEED = 20261003
BOOT = 10000
LEVEL = 0.975
GATE_MS = 2.0


def paired_gate(cr: list[float], comp: list[float], level: float = LEVEL, seed: int = SEED,
                boot: int = BOOT) -> dict[str, Any]:
    """Median of d = cr - comp with a two-sided ``level`` seeded paired bootstrap CI."""
    d = [x - y for x, y in zip(cr, comp)]
    n = len(d)
    out: dict[str, Any] = {"n": n, "median": statistics.median(d) if d else None, "ci": None, "level": level,
                           "seed": seed, "resamples": boot, "min": min(d) if d else None,
                           "max": max(d) if d else None, "positive": sum(1 for x in d if x > 0)}
    if n < 2:
        return out
    rng = random.Random(seed)
    vals = sorted(statistics.median([d[rng.randrange(n)] for _ in range(n)]) for _ in range(boot))
    a = (1.0 - level) / 2.0
    out["ci"] = [vals[int(math.floor(a * (len(vals) - 1)))], vals[int(math.ceil((1.0 - a) * (len(vals) - 1)))]]
    return out
