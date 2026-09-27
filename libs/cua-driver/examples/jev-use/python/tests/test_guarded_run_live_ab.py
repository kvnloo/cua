"""The guarded-run harness must use the fixture oracle and the bound-completion rule."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[6]
SCRIPT = ROOT / "scripts/repro/guarded_run_live_ab.py"


def load():
    spec = importlib.util.spec_from_file_location("guarded_run_live_ab", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GuardedRunLiveAbTest(unittest.TestCase):
    def test_local_fixture_stops_every_negative_and_verifies_the_allowed_submit(self) -> None:
        rows = load().local_rows(ROOT)
        by_key = {(row["arm"], row["case"]): row for row in rows}
        negatives = [
            row
            for row in rows
            if row["arm"] == "guarded-run" and row["case"] != "type then submit"
            and row["case"] != "one executable reobserve"
        ]
        self.assertGreaterEqual(len(negatives), 8)
        for row in negatives:
            self.assertEqual(row["second_dispatch"], 0, row["case"])
            self.assertIsNone(row["oracle"]["submitted"], row["case"])
        allowed = by_key[("guarded-run", "type then submit")]
        self.assertEqual(allowed["second_reason"], "allowed")
        self.assertEqual(allowed["second_dispatch"], 1)
        self.assertFalse(allowed["provider_called_on_second"])
        self.assertEqual(allowed["oracle"]["submitted"], allowed["token"])
        self.assertEqual(allowed["outcome"], "verified")
        reobserve = by_key[("guarded-run", "one executable reobserve")]
        self.assertEqual(reobserve["route"], "chooser")
        self.assertTrue(reobserve["provider_called_on_second"])
        self.assertEqual(reobserve["second_dispatch"], 0)
        self.assertIsNone(reobserve["oracle"]["submitted"])
        baseline = by_key[("baseline", "type then submit")]
        self.assertEqual(baseline["provider_calls"], 2)
        self.assertTrue(baseline["provider_called_on_second"])
        self.assertEqual(baseline["oracle"]["submitted"], baseline["token"])


if __name__ == "__main__":
    unittest.main()
