"""A/A summary: sigma/tau/n arithmetic, CI-includes-zero, T_act fallback, PSI fence."""

from __future__ import annotations

import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from areval import aa, stats  # noqa: E402
import synth  # noqa: E402

MS = 1_000_000


def aa_rows(n_pairs: int, sigma_ln: float, act_sigma_ln: float | None = None, seed: int = 1,
            psi_outlier: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    tid = 0
    for k in range(n_pairs):
        base = 500.0 * math.exp(rng.gauss(0, 0.02))
        order = "AB" if k % 2 == 0 else "BA"
        arms = [("champion", base), ("candidate", base * math.exp(rng.gauss(0, sigma_ln)))]
        if order == "BA":
            arms.reverse()
        for pos, (arm, t) in enumerate(arms):
            r = synth.trial(tid, arm, "task", t, None, trace=True, pair=f"p{k}", order=order, position=pos,
                            session=k // 24)
            # T_act = done - first click m0: a 300 ms act with its own noise.
            act = 300.0 * math.exp(rng.gauss(0, act_sigma_ln if act_sigma_ln is not None else sigma_ln))
            r["t_done_ns"] = int(t * MS)
            r["t_exit_ns"] = r["t_done_ns"] + 5 * MS
            r["calls"] = [{"tool": "get_window_state", "m0": 0}, {"tool": "click", "m0": int((t - act) * MS)}]
            stall = 2000.0 if psi_outlier is not None and k == psi_outlier else 50.0 + rng.random() * 20
            r["psi"] = {"cpu_some_stall_us": stall}
            rows.append(r)
            tid += 1
    for arm in ("champion", "candidate"):
        for kind in ("stale_negative", "impossible_canary"):
            rows.append(synth.trial(tid, arm, kind, None))
            tid += 1
    return rows


class AASummary(unittest.TestCase):
    def test_quiet_aa(self):
        out = aa.summarize(aa_rows(72, 0.01))
        w = out["whole_task_T"]
        self.assertEqual(w["pairs"], 72)
        self.assertTrue(w["ci_includes_zero"])
        self.assertAlmostEqual(w["tau"], max(0.02, math.exp(w["abs_delta_aa_q975_ln"]) - 1))
        self.assertEqual(w["n_pairs_required"], stats.n_pairs_required(w["sigma_ln"], w["tau"]))
        self.assertEqual(out["decision_metric"], "T_act")
        self.assertEqual(out["guardrail"]["metric"], "T")
        self.assertEqual(out["guardrail"]["tau"], w["tau"])
        self.assertTrue(out["gates_on_aa"]["G2"]["pass"], out["gates_on_aa"]["G2"]["reasons"][:3])
        self.assertTrue(out["gates_on_aa"]["G3"]["pass"])
        self.assertTrue(out["gates_on_aa"]["G4"]["pass"])
        self.assertFalse(out["gates_on_aa"]["G5_false_keep_check"]["pass"])

    def test_t_act_decides_whole_task_guards(self):
        # Pre-registered in the fix round: T_act is the decision metric whatever whole-task T's
        # sigma; whole-task T is the guardrail with its own A/A tau.
        out = aa.summarize(aa_rows(72, 0.15, act_sigma_ln=0.01))
        self.assertEqual(out["decision_metric"], "T_act")
        self.assertEqual(out["chosen"]["tau"], out["T_act"]["tau"])
        self.assertEqual(out["chosen"]["n_pairs"], out["T_act"]["n_pairs_required"])
        self.assertGreater(out["guardrail"]["tau"], out["T_act"]["tau"])

    def test_self_consistent_tau_is_the_floor(self):
        # At the evaluation's own size n = n_required(tau), q975|Delta_AA| ~ 0.62 ln(1+tau) < ln(1+tau),
        # so the self-consistent tau is the 2% floor.
        w = aa.summarize(aa_rows(72, 0.03))["whole_task_T"]
        self.assertAlmostEqual(w["tau_self_consistent"], 0.02)
        self.assertEqual(w["n_pairs_required_self_consistent"], stats.n_pairs_required(w["sigma_ln"], 0.02))

    def test_psi_fence_flags_an_outlier_pair(self):
        out = aa.summarize(aa_rows(72, 0.01, psi_outlier=5))
        self.assertEqual(out["psi"]["aa_pairs_discarded"], 1)


if __name__ == "__main__":
    unittest.main()
