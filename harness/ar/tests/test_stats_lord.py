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

    def test_sign_flip_p_direction(self):
        self.assertLess(stats.sign_flip_p_less([-0.1 + 0.01 * (i % 3) for i in range(30)], 20000, seed=1), 0.01)
        self.assertGreater(stats.sign_flip_p_less([0.1 + 0.01 * (i % 3) for i in range(30)], 20000, seed=1), 0.5)

    def test_sign_flip_p_floor_is_one_over_b_plus_one(self):
        # All 38 pairs negative: the exact p is 2^-38, the Monte Carlo p sits at its floor.
        self.assertEqual(stats.sign_flip_p_less([-0.08] * 38, 50000, seed=2), 1 / 50001)

    def test_sign_flip_p_matches_exact_enumeration(self):
        import itertools
        xs = [-0.05, 0.02, -0.03, -0.04, 0.01, -0.02, -0.06, 0.03, -0.01, -0.07]
        obs = sum(xs)
        exact = sum(1 for s in itertools.product((1, -1), repeat=len(xs))
                    if sum(a * abs(x) for a, x in zip(s, xs)) <= obs + 1e-12) / 2 ** len(xs)
        self.assertAlmostEqual(stats.sign_flip_p_less(xs, 200000, seed=3), exact, delta=0.003)

    def test_sign_flip_resamples_resolve_the_level(self):
        for alpha in (1.25e-3, 2.3e-4, 3.2e-5, 1e-6):
            b = stats.sign_flip_resamples(alpha)
            self.assertGreaterEqual(b, 10 / alpha)
            self.assertGreaterEqual(b, stats.SIGN_FLIP_MIN_RESAMPLES)


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

    def test_next_alpha_depends_only_on_the_past(self):
        prior = [1e-9, 0.3, 0.002]
        self.assertEqual(lord.next_alpha(prior), lord.decide(prior, 0.9)["alpha_i"])
        self.assertEqual(lord.next_alpha(prior), lord.decide(prior, 1e-12)["alpha_i"])
        # The levels the F2 fix must resolve: alpha_3 = 2.3e-4 < 1/4001 after two misses.
        self.assertLess(lord.next_alpha([0.5, 0.5]), 1 / 4001)

    def test_decide_matches_replay(self):
        prior = [1e-9, 0.3, 0.002]
        self.assertEqual(lord.decide(prior, 0.01), lord.replay([*prior, 0.01])[-1])


if __name__ == "__main__":
    unittest.main()
