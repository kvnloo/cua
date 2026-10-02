from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from areval import lord, stats  # noqa: E402


class Stats(unittest.TestCase):
    def test_quantile_matches_type7(self):
        self.assertEqual(stats.quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertAlmostEqual(stats.quantile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9), 9.1)

    def test_n_pairs_formula(self):
        # (z_.99 + z_.80)^2 = 10.04: the plan's "10 (sigma/delta)^2" at delta = ln(1+tau).
        self.assertAlmostEqual(stats.z_sum() ** 2, 10.04, places=2)
        sigma, tau = 0.05, 0.02
        n = stats.n_pairs_required(sigma, tau)
        self.assertEqual(n, math.ceil(stats.z_sum() ** 2 * (sigma / math.log1p(tau)) ** 2))
        self.assertGreater(stats.achieved_power(sigma, tau, n), 0.79)

    def test_tau_floor_and_aa_noise(self):
        quiet = stats.tau_from_aa([0.001, -0.001] * 20, batch=20)
        self.assertEqual(quiet["tau"], 0.02)
        noisy = stats.tau_from_aa([0.2, -0.2, 0.1, -0.15] * 10, batch=5)
        self.assertGreater(noisy["tau"], 0.02)

    def test_bootstrap_p_direction(self):
        self.assertLess(stats.bootstrap_p_less([-0.1 + 0.01 * (i % 3) for i in range(30)]), 0.01)
        self.assertGreater(stats.bootstrap_p_less([0.1 + 0.01 * (i % 3) for i in range(30)]), 0.5)


class Lord(unittest.TestCase):
    def test_first_level_and_gamma_sum(self):
        first = lord.replay([1.0])[0]
        self.assertAlmostEqual(first["alpha_i"], lord.W0 * lord.gamma(1))
        self.assertLessEqual(sum(lord.gamma(j) for j in range(1, 200000)), 1.0)

    def test_rejection_raises_later_levels_and_wealth(self):
        no = lord.replay([1.0, 1.0, 1.0])
        yes = lord.replay([1e-9, 1.0, 1.0])
        self.assertTrue(yes[0]["rejected"])
        self.assertGreater(yes[1]["alpha_i"], no[1]["alpha_i"])
        self.assertAlmostEqual(yes[0]["wealth_after"], lord.W0 - yes[0]["alpha_i"] + (lord.ALPHA - lord.W0))

    def test_wealth_never_negative(self):
        out = lord.replay([0.5] * 500)
        self.assertTrue(all(o["wealth_after"] >= 0 for o in out))
        self.assertEqual([o["index"] for o in out[:3]], [1, 2, 3])

    def test_decide_matches_replay(self):
        prior = [1e-9, 0.3, 0.002]
        self.assertEqual(lord.decide(prior, 0.01), lord.replay([*prior, 0.01])[-1])


if __name__ == "__main__":
    unittest.main()
