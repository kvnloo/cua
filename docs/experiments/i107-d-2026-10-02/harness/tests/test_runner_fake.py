"""End-to-end harness test: the real jev-use run.run (A and D) through run_d.py with the fake Driver.

No browser and no Driver binary; every trial is labelled UNIT_FAKE_DRIVER.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import d_analysis as D  # noqa: E402
import i107_fixture as fx  # noqa: E402
import run_d as R  # noqa: E402


def spec(arm: str, *, control: str | None = None, condition: str = "W-quiet", cohort: str = "K1",
         pair: str = "t-p000", name: str | None = None) -> dict:
    return {"name": name or f"t-{(control or condition.replace('W-', '')).lower()}-{arm}", "block": "t", "plan": "unit",
            "pair": pair, "order": "AD", "arm": arm, "condition": condition,
            "variant": "control" if control else {"W-quiet": "quiet", "W-churn": "churn"}[condition],
            "cohort": cohort, "comparison": "controls" if control else "CMP-D",
            "kind": "control" if control else "measured", "control": control}


class FakeRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = fx.make_server(0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/"
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.records: dict[str, dict] = {}
        opts = R.Options(driver="fake", out=cls.out, binary_sha256="0" * 64, caller_tree="f" * 40,
                         lock_label="unit", fake=True)
        specs = [spec("A"), spec("D"), spec("A", condition="W-churn", pair="t-p001"),
                 spec("D", condition="W-churn", pair="t-p001"),
                 spec("D", control="DC01"), spec("A", control="DC03"), spec("D", control="DC03"),
                 spec("D", control="DC06"), spec("A", control="DC06"), spec("D", control="DC10"),
                 spec("D", control="DC05b"), spec("D", control="DC07"), spec("A", cohort="K2", name="t-k2-A")]
        for s in specs:
            cls.records[s["name"]] = asyncio.run(R.run_trial(s, opts, cls.url))
        cls.trials = {t["name"]: t for t in D.load_trials(cls.out / "trials")}

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def t(self, name: str) -> dict:
        return self.trials[name]

    def test_arm_a_and_d_paths_and_work_deleted(self) -> None:
        a, d = D.counts(self.t("t-quiet-A")), D.counts(self.t("t-quiet-D"))
        self.assertEqual(self.t("t-quiet-A")["summary"]["outcome"], "verified")
        self.assertEqual(self.t("t-quiet-D")["summary"]["outcome"], "verified")
        self.assertEqual((a["decisions"], d["decisions"]), (2, 1))
        self.assertEqual(a["decision_routes"], ["provider", "provider"])
        self.assertEqual(d["decision_routes"], ["provider", "guarded-completion"])
        self.assertEqual((a["plan_calls"], a["resolve_calls"]), (0, 0))
        self.assertEqual((d["plan_calls"], d["resolve_calls"], d["plans_bound"]), (1, 1, 1))
        self.assertEqual(d["guard"][0]["status"], "accepted")
        self.assertEqual((a["snapshots_full"], d["snapshots_full"]), (2, 2))
        self.assertEqual((a["driver_mutations"], d["driver_mutations"]), (2, 2))
        self.assertEqual(a["cdp_sends_by_method"], d["cdp_sends_by_method"])

    def test_cursor_disabled_before_prepare_in_both_arms(self) -> None:
        for name in ("t-quiet-A", "t-quiet-D"):
            sends = [e for e in self.t(name)["events"] if e["event"] == "call_send"]
            self.assertEqual([e["tool"] for e in sends[:2]], ["set_agent_cursor_enabled", "browser_prepare"])
            self.assertEqual(self.t(name)["summary"]["cursor_ack"], {"requested": False, "ok": True})

    def test_trials_are_valid_and_decomposable(self) -> None:
        for name in ("t-quiet-A", "t-quiet-D", "t-churn-A", "t-churn-D", "t-k2-A"):
            self.assertEqual(D.validity(self.t(name)), [], name)
            r = D.decompose_d(self.t(name))
            self.assertIsNotNone(r, name)
            self.assertAlmostEqual(sum(r["spans10"].values()), r["T_ms"], places=3)
        labels = [e["label"] for e in self.t("t-quiet-D")["events"] if e["event"] == "call_send"]
        for want in ("snapshot1", "action1", "snapshot2", "action2", "bind", "navigate", "prepare"):
            self.assertIn(want, labels)

    def test_cleanup_resources_and_environment_records(self) -> None:
        s = self.t("t-quiet-A")["summary"]
        c = D.cleanup_spans(self.t("t-quiet-A"))
        self.assertIsNotNone(c["session_close_ms"])
        self.assertIsNotNone(c["lifetime_ms"])
        for key in ("psi_before", "psi_after", "loadavg_before", "loadavg_after", "resources", "trial_wall_ns",
                    "token_sha16", "token_len", "evidence", "lock_label", "binary_sha256", "caller_tree"):
            self.assertIn(key, s)
        self.assertEqual(s["evidence"], "UNIT_FAKE_DRIVER")
        self.assertEqual(s["network"]["non_loopback_connect_attempts"], 0)
        self.assertEqual(self.t("t-k2-A")["summary"]["token_len"], 64)
        self.assertEqual(self.t("t-churn-A")["summary"]["fixture_variant"], "churn")

    def test_no_token_in_any_written_file(self) -> None:
        tokens = [r["_token"] for r in self.records.values()]
        for path in self.out.rglob("*"):
            if path.is_file():
                text = path.read_text()
                for tok in tokens:
                    self.assertNotIn(tok, text, path.name)

    def test_dc01_guard_declines_field_not_proven_then_recovers(self) -> None:
        c = D.counts(self.t("t-dc01-D"))
        self.assertEqual(c["guard"][0], {"status": "declined", "reason": "field_not_proven"})
        self.assertEqual(c["candidates"][:2], ["type-verification-value", "type-verification-value"])
        self.assertTrue(D.oracle_satisfied(self.t("t-dc01-D")["summary"]))
        ctl = [e for e in self.t("t-dc01-D")["events"] if e["event"] == "control_acked"]
        self.assertTrue(ctl and ctl[0]["acked"] and ctl[0]["applied"])

    def test_dc03_competing_submit(self) -> None:
        self.assertEqual(D.counts(self.t("t-dc03-D"))["guard"][0]["reason"], "submit_not_unique")
        self.assertGreaterEqual(D.counts(self.t("t-dc03-A"))["wrong_target_submits"], 1)  # first match = competing

    def test_dc06_lookalike_is_a_wrong_target_in_both_arms_and_revises_d(self) -> None:
        cd, ca = D.counts(self.t("t-dc06-D")), D.counts(self.t("t-dc06-A"))
        self.assertEqual(cd["guard"][0]["status"], "accepted")
        self.assertGreaterEqual(min(cd["wrong_target_submits"], ca["wrong_target_submits"]), 1)
        zero = D.required_zero(list(self.trials.values()))
        self.assertGreaterEqual(zero["D"]["wrong_target_effect"], 1)
        disp = D.disposition({"W-quiet": {"verdict": "NO_MEANINGFUL_BENEFIT"}}, zero, decisions_deleted=1.0)
        self.assertTrue(disp["disposition"].startswith("REVISE"))

    def test_dc10_probe_in_a_new_session_is_refused_without_effect(self) -> None:
        s = self.t("t-dc10-D")["summary"]
        self.assertEqual(s["probe"]["code"], "browser_binding_stale")
        self.assertEqual(s["probe"]["submits_during_probe"], 0)
        self.assertTrue(D.oracle_satisfied(s))

    def test_dc05b_detached_click_is_recorded_as_driver_stale_acceptance(self) -> None:
        c = D.counts(self.t("t-dc05b-D"))
        self.assertEqual(c["detached_clicks"], 1)
        self.assertEqual(D.required_zero([self.t("t-dc05b-D")])["D"]["driver_stale_acceptance"], 1)

    def test_dc07_document_replacement_refused_stale_before_dispatch(self) -> None:
        t = self.t("t-dc07-D")
        codes = [e.get("code") for e in t["events"] if e["event"] == "call_return" and e.get("tool") == "browser_click"]
        self.assertEqual(codes, ["browser_ref_stale"])
        self.assertEqual(t["summary"]["outcome"], "unknown")
        self.assertEqual(D.counts(t)["journal_submits"], 0)
        self.assertTrue(any(e["event"] == "control_settled" and e["hit"] for e in t["events"]))

    def test_ledger_row_has_the_10_fields(self) -> None:
        row = D.ledger_row(self.t("t-quiet-D"), lane="i107-d")
        for key in ("lane", "comparison", "condition", "cohort", "regime", "pair", "order", "arm", "binary_sha256",
                    "caller_tree", "token_sha16", "outcome", "oracle_verified", "decision_routes", "guard", "counts",
                    "spans10", "T_oracle_ms", "T_runner_ms", "cleanup", "resources", "loadavg_before", "psi_before",
                    "lock_label", "control", "excluded", "validity", "evidence", "chooser"):
            self.assertIn(key, row)
        self.assertEqual(row["chooser"], "choose_mock_for_task (scripted mock; FIXTURE/BENCHMARK, never LIVE_PROVIDER)")
        json.dumps(row)


if __name__ == "__main__":
    unittest.main()
