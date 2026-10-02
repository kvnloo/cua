"""Each gate: one passing and at least one failing synthetic case. Run: python3 -m unittest discover harness/ar/tests"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from areval import gates  # noqa: E402
from areval.g0 import g0  # noqa: E402
from areval.scanner import load_rules  # noqa: E402
import synth  # noqa: E402

RULES = load_rules()


def first(rows, **match):
    return next(r for r in rows if all(r.get(k) == v for k, v in match.items()))


class G0(unittest.TestCase):
    def run_g0(self, **over):
        return g0(synth.g0_inputs(**over), synth.ALLOW, synth.MANIFEST, RULES)

    def test_pass_allowed_constant_edit(self):
        r = self.run_g0()
        self.assertTrue(r["pass"], r["reasons"])

    def test_fail_cargo_change(self):
        r = self.run_g0(diff=synth.diff() + synth.diff("libs/cua-driver/rust/Cargo.toml", "a = 1", "a = 2"))
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith("cargo_change") for x in r["reasons"]))

    def test_fail_path_outside_allowlist(self):
        r = self.run_g0(diff=synth.diff("libs/cua-driver/rust/crates/platform-linux/src/x11/mod.rs"))
        self.assertTrue(any(x.startswith("path_outside_allowlist") for x in r["reasons"]))

    def test_fail_harness_touched(self):
        r = self.run_g0(diff=synth.diff("harness/ar/areval/gates.py", "x = 1", "x = 2"))
        self.assertTrue(any(x.startswith("harness_touched") for x in r["reasons"]))

    def test_fail_phase_trace_line(self):
        r = self.run_g0(diff=synth.diff(removed='cua_driver_core::phase_trace::mark("focus_guard", "restored");',
                                        added="let _ = 1;"))
        self.assertTrue(any(x.startswith("phase_trace_line_touched") for x in r["reasons"]))

    def test_fail_itemcheck_violation(self):
        bad = copy.deepcopy(synth.g0_inputs()["itemcheck"])
        bad["ok"] = False
        bad["violations"] = [{"file": synth.FG, "kind": "item_changed_not_allowed", "item": "fn guarded", "detail": ""}]
        r = self.run_g0(itemcheck=bad)
        self.assertTrue(any("item_changed_not_allowed" in x for x in r["reasons"]))

    def test_fail_test_item_hash(self):
        bad = copy.deepcopy(synth.g0_inputs()["itemcheck"])
        bad["files"][synth.FG]["test_items_cand"] = {"mod tests::fn t": "c" * 64}
        r = self.run_g0(itemcheck=bad)
        self.assertTrue(any(x.startswith("test_item_hash_mismatch") for x in r["reasons"]))

    def test_fail_frozen_file(self):
        r = self.run_g0(frozen_sha256={"libs/cua-driver/rust/Cargo.lock": "f" * 64})
        self.assertTrue(any(x.startswith("frozen_file_changed") for x in r["reasons"]))

    def test_fail_scanner(self):
        r = self.run_g0(diff=synth.diff(added="const SETTLE_WATCH: Duration = Duration::ZERO;"))
        self.assertTrue(any(x.startswith("scanner:comparison_tricks") for x in r["reasons"]))

    def test_fail_lineage(self):
        r = self.run_g0(lineage_ok=False)
        self.assertIn("candidate_not_based_on_champion", r["reasons"])


class G1(unittest.TestCase):
    req = ["cua-driver-core --lib", "platform-linux --lib"]

    def test_pass(self):
        self.assertTrue(gates.g1(synth.build_rows(), self.req)["pass"])

    def test_fail_failed_suite(self):
        r = gates.g1(synth.build_rows(ok=False), self.req)
        self.assertFalse(r["pass"])
        self.assertIn("suite_failed:platform-linux --lib", r["reasons"])

    def test_fail_missing(self):
        self.assertFalse(gates.g1(synth.build_rows()[:2], self.req)["pass"])


class G2(unittest.TestCase):
    def test_pass(self):
        r = gates.g2(synth.rows(), synth.prereg())
        self.assertTrue(r["pass"], r["reasons"][:5])

    def check(self, mutate, prefix):
        rows = synth.rows()
        mutate(rows)
        r = gates.g2(rows, synth.prereg())
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith(prefix) for x in r["reasons"]), r["reasons"][:5])

    def test_fail_duplicate_mutation(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task").update(seq_delta=2),
                   "duplicate_or_missing_mutation")

    def test_fail_unverified_success(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task").update(verified=False),
                   "unverified_success")

    def test_fail_stale_dispatch(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="stale_negative").update(claimed_success=True),
                   "stale_dispatch_accepted")

    def test_fail_blind_replay(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task").update(dispatch_calls=2),
                   "blind_replay_dispatch")

    def test_fail_new_file(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task")["footprint"]["home_files"].append(
            "/home/trial/settle.cache"), "new_file")

    def test_fail_new_socket(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task")["footprint"].update(sockets=8), "new_socket")

    def test_fail_new_process(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task")["footprint"].update(procs=3), "new_process")

    def test_fail_route(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task").update(route="xtest"),
                   "provenance_route_mismatch")

    def test_fail_journal_after_done(self):
        self.check(lambda rows: first(rows, arm="candidate", kind="task").update(journal_before_done=False),
                   "journal_after_done")


class G3(unittest.TestCase):
    def test_pass(self):
        self.assertTrue(gates.g3(synth.rows())["pass"])

    def test_fail_negative_accepted(self):
        rows = synth.rows()
        first(rows, arm="candidate", kind="stale_negative").update(refused=False, claimed_success=True, seq_delta=1)
        self.assertFalse(gates.g3(rows)["pass"])

    def test_fail_canary_claimed(self):
        rows = synth.rows()
        first(rows, arm="champion", kind="impossible_canary").update(canary_outcome="claimed_success")
        self.assertFalse(gates.g3(rows)["pass"])

    def test_fail_missing_controls(self):
        rows = [r for r in synth.rows() if r["kind"] != "impossible_canary"]
        self.assertFalse(gates.g3(rows)["pass"])


class G4(unittest.TestCase):
    def test_pass(self):
        self.assertTrue(gates.g4(synth.rows())["pass"])

    def test_fail_verified_counts_differ(self):
        rows = synth.rows()
        first(rows, arm="candidate", kind="task").update(verified=False, failure="verify_timeout")
        r = gates.g4(rows)
        self.assertFalse(r["pass"])
        self.assertTrue(r["reasons"][0].startswith("verified_differ"))


class G5(unittest.TestCase):
    def test_pass_real_effect(self):
        r = gates.g5(synth.rows(effect_ln=-0.10), synth.prereg(), [])
        self.assertTrue(r["pass"], r["reasons"])
        self.assertEqual(r["metrics"]["lord"]["index"], 1)
        self.assertTrue(r["metrics"]["lord"]["rejected"])

    def test_fail_no_effect(self):
        r = gates.g5(synth.rows(effect_ln=0.0), synth.prereg(), [])
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith("not_significant") for x in r["reasons"]))

    def test_fail_effect_below_tau(self):
        # Significant but smaller than ln(1+tau): tiny noise, effect -1%.
        r = gates.g5(synth.rows(effect_ln=-0.01, sigma=0.001), synth.prereg(), [])
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith("effect_below_tau") for x in r["reasons"]), r["reasons"])

    def test_inconclusive_when_underpowered(self):
        r = gates.g5(synth.rows(n_pairs=10), synth.prereg(), [])
        self.assertFalse(r["pass"])
        self.assertTrue(r["metrics"]["inconclusive"])


class G6(unittest.TestCase):
    def test_pass(self):
        self.assertTrue(gates.g6(synth.rows(), 0.02)["pass"])

    def test_fail_tail(self):
        rows = synth.rows(effect_ln=-0.05)
        cand = [r for r in rows if r["kind"] == "task" and r["arm"] == "candidate"]
        for r in cand[: len(cand) // 5]:
            r["T_ns"] *= 3
        r = gates.g6(rows, 0.02)
        self.assertFalse(r["pass"])


class G7(unittest.TestCase):
    def test_pass_mechanism(self):
        r = gates.g7(synth.rows(sigma=0.005), synth.prereg())
        self.assertTrue(r["pass"], r["reasons"])

    def test_fail_saving_elsewhere(self):
        r = gates.g7(synth.rows(sigma=0.005, phase_share=0.3), synth.prereg())
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith("mechanism_share") for x in r["reasons"]))

    def test_fail_trace_off_disagrees(self):
        r = gates.g7(synth.rows(sigma=0.005, off_effect_ln=0.0), synth.prereg())
        self.assertFalse(r["pass"])
        self.assertTrue(any(x.startswith("trace_off_disagrees") for x in r["reasons"]))

    def test_fail_marks_missing(self):
        rows = synth.rows(sigma=0.005)
        first(rows, arm="candidate", kind="task", trace=True).pop("marks")
        self.assertFalse(gates.g7(rows, synth.prereg())["pass"])


class G8(unittest.TestCase):
    other = ["libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs"]

    def test_pass_300(self):
        self.assertTrue(gates.g8(synth.rows(soak=300), self.other, synth.ALLOW, synth.prereg())["pass"])

    def test_fail_short(self):
        self.assertFalse(gates.g8(synth.rows(soak=299), self.other, synth.ALLOW, synth.prereg())["pass"])

    def test_fail_focus_guard_needs_1000(self):
        r = gates.g8(synth.rows(soak=300), [synth.FG], synth.ALLOW, synth.prereg())
        self.assertFalse(r["pass"])
        self.assertEqual(r["metrics"]["required"], 1000)

    def test_fail_one_failure(self):
        rows = synth.rows(soak=300)
        first(rows, kind="soak").update(verified=False, failure="verify_timeout")
        self.assertFalse(gates.g8(rows, self.other, synth.ALLOW, synth.prereg())["pass"])


class GS(unittest.TestCase):
    def test_pass(self):
        r = gates.gs(synth.rows(), synth.prereg())
        self.assertTrue(r["pass"], r["reasons"])

    def test_fail_not_run(self):
        rows = [r for r in synth.rows() if r["kind"] != "spot_browser_fill_submit"]
        r = gates.gs(rows, synth.prereg())
        self.assertIn("spot_not_run:spot_browser_fill_submit", r["reasons"])

    def test_fail_slower(self):
        r = gates.gs(synth.rows(spot_effect_ln=0.10), synth.prereg())
        self.assertFalse(r["pass"])


class Pipeline(unittest.TestCase):
    def evaluate(self, rows, g0_over=None, prior=()):
        return gates.evaluate(synth.prereg(), rows, synth.build_rows(), synth.g0_inputs(**(g0_over or {})),
                              synth.ALLOW, synth.MANIFEST, RULES, list(prior))

    def test_keep(self):
        # A native.rs-only change needs 300 soak trials.
        d = synth.diff("libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs",
                       "tokio::time::sleep(Duration::from_millis(50)).await;",
                       "tokio::time::sleep(Duration::from_millis(10)).await;")
        allow = {"items": {**synth.ALLOW["items"],
                           "libs/cua-driver/rust/crates/platform-linux/src/atspi/native.rs": ["fn perform_action_ref"]},
                 "soak_1000_files": synth.ALLOW["soak_1000_files"]}
        out = gates.evaluate(synth.prereg(), synth.rows(sigma=0.005), synth.build_rows(), synth.g0_inputs(diff=d),
                             allow, synth.MANIFEST, RULES, [])
        self.assertEqual(out["verdict"], "KEEP", [g["reasons"] for g in out["gates"]])
        self.assertEqual([g["gate"] for g in out["gates"]], list(gates.GATE_ORDER))

    def test_reject_stops_at_first_failure(self):
        out = self.evaluate(synth.rows(), {"lineage_ok": False})
        self.assertEqual((out["verdict"], out["failed_gate"]), ("REJECT", "G0"))
        self.assertEqual(len(out["gates"]), 1)
        self.assertIsNone(out["lord"])  # no alpha index consumed before G5

    def test_inconclusive(self):
        out = self.evaluate(synth.rows(n_pairs=10))
        self.assertEqual((out["verdict"], out["failed_gate"]), ("INCONCLUSIVE", "G5"))


if __name__ == "__main__":
    unittest.main()
