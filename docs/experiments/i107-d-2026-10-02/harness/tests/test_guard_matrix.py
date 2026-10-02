"""UNIT: PR 4316 guard and arm-A candidate logic over control-shaped semantic_v2 snapshots."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import guard_matrix as G  # noqa: E402


class GuardMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = G.compute()
        cls.by = {(r["control"], r["branch"]): r for r in cls.rows}

    def row(self, control: str, branch: str = "only") -> dict:
        return self.by[(control, branch)]

    def test_baseline_accepts_with_the_fresh_ref_and_deletes_one_decision(self) -> None:
        r = self.row("baseline")
        self.assertEqual(r["D"]["guard"], {"status": "accepted", "reason": None})
        self.assertEqual(r["D"]["target"], "real")
        self.assertEqual(r["A"]["target"], "real")
        self.assertEqual(r["D"]["decisions_step2"], 0)
        self.assertEqual(r["A"]["decisions_step2"], 1)

    def test_field_changed_declines_field_not_proven(self) -> None:
        for cid in ("DC01", "DC17a"):
            r = self.row(cid)
            self.assertEqual(r["D"]["guard"]["reason"], "field_not_proven", cid)
            self.assertEqual(r["D"]["choice"], "type-verification-value", cid)
            self.assertEqual(r["A"]["choice"], "type-verification-value", cid)

    def test_competing_submit_declines_and_arm_a_takes_the_first_match(self) -> None:
        r = self.row("DC03")
        self.assertEqual(r["D"]["guard"]["reason"], "submit_not_unique")
        self.assertEqual(r["A"]["target"], "competing")  # inserted before the original
        self.assertEqual(r["D"]["target"], "competing")  # fallback chooser = arm A logic

    def test_removed_submit_declines(self) -> None:
        r = self.row("DC04")
        self.assertEqual(r["D"]["guard"]["reason"], "submit_not_unique")
        self.assertIsNone(r["A"]["target"])

    def test_benign_rerender_accepts_a_fresh_ref(self) -> None:
        r = self.row("DC05a")
        self.assertEqual(r["D"]["guard"]["status"], "accepted")
        self.assertNotEqual(r["D"]["fresh_ref"], r["D"]["prior_ref"])

    def test_relocated_lookalike_is_accepted_missing_scope_fact(self) -> None:
        r = self.row("DC06")
        self.assertEqual(r["D"]["guard"]["status"], "accepted")
        self.assertEqual(r["D"]["target"], "decoy")
        self.assertEqual(r["A"]["target"], "decoy")
        self.assertIn("form", r["missing_fact"])

    def test_check_to_dispatch_controls_are_invisible_to_the_guard(self) -> None:
        for cid in ("DC05b", "DC07", "DC10", "DC14b", "DC20a", "DC20b"):
            r = self.row(cid)
            self.assertEqual(r["D"]["guard"]["status"], "accepted", cid)
            self.assertEqual(r["outcome_owner"], "driver_or_fixture", cid)

    def test_driver_dependent_controls_have_both_branches(self) -> None:
        expect = {
            ("DC12", "submit_omitted_css_hidden"): "declined",
            ("DC13", "submit_kept_offscreen"): "accepted",
            ("DC14a", "submit_omitted_page_occluded"): "declined",
            ("DC14a", "submit_kept"): "accepted",
            ("DC16a", "ax_disabled_no_actions"): "declined",
            ("DC16a", "ax_enabled"): "accepted",
            ("DC16b", "ax_disabled_no_actions"): "declined",
            ("DC16b", "ax_enabled"): "accepted",
            ("DC17b", "ax_name_includes_before"): "declined",
            ("DC17b", "ax_name_unchanged"): "accepted",
        }
        for key, status in expect.items():
            self.assertEqual(self.by[key]["D"]["guard"]["status"], status, key)
            self.assertEqual(self.by[key]["evidence"], "UNIT (branch conditional on Driver/Chrome; REAL BLOCKED)")

    def test_rows_are_json_and_token_free(self) -> None:
        text = json.dumps(self.rows, sort_keys=True)
        self.assertNotIn(G.TOKEN, text)
        self.assertEqual(json.loads(text), self.rows)


if __name__ == "__main__":
    unittest.main()
