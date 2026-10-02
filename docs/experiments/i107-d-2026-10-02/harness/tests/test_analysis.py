"""Unit tests for lane-D analysis (d_analysis.py) on synthetic trials."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import d_analysis as D  # noqa: E402

MS = 1_000_000


def synth(arm: str = "D", *, t0: int = 1_000 * MS, ledger: bool = True, guard: str = "accepted",
          submits: int = 1, wrong: int = 0, poller_ms: float | None = 60.0, outcome: str = "verified",
          settle: int = 100, cursor_marks: bool = False, pair: str = "cmpd-p000", condition: str = "W-quiet",
          control: str | None = None, load1: float = 1.0) -> dict:
    """A fill->submit trial: snapshot1 [0,10] cand [10,11] decide [11,12] plan [12,13] action1 [13,25]
    snapshot2 [25,33] cand [33,34] guard|decide [34,35] action2 [35,50], effect at 49, verify read [52,53]."""
    def t(ms: float) -> int:
        return t0 + int(ms * MS)

    ev = [{"event": "trial_start", "t_mono_ns": t0 - 500 * MS},
          {"event": "call_send", "label": "navigate", "tool": "browser_navigate", "t_mono_ns": t0 - 100 * MS},
          {"event": "call_return", "label": "navigate", "tool": "browser_navigate", "ok": True, "t_mono_ns": t0 - 50 * MS},
          {"event": "oracle_send", "label": "o1", "t_mono_ns": t0 - 2 * MS},
          {"event": "oracle_return", "label": "o1", "outcome": "unknown", "t_mono_ns": t0 - 1 * MS},
          {"event": "call_send", "label": "snapshot1", "tool": "get_browser_state", "snapshot_format": "semantic_v2",
           "has_query": False, "t_mono_ns": t(0)},
          {"event": "call_return", "label": "snapshot1", "tool": "get_browser_state", "ok": True, "bytes": 3000,
           "n_refs": 2, "t_mono_ns": t(10)},
          {"event": "cand_start", "t_mono_ns": t(10)}, {"event": "cand_done", "t_mono_ns": t(11)},
          {"event": "decide_start", "t_mono_ns": t(11)}, {"event": "decided", "choice": "type-verification-value", "t_mono_ns": t(12)},
          *([{"event": "plan_start", "t_mono_ns": t(12)}, {"event": "plan_done", "bound": True, "t_mono_ns": t(13)}]
            if arm == "D" else []),
          {"event": "call_send", "label": "action1", "tool": "browser_type", "t_mono_ns": t(13)},
          {"event": "call_return", "label": "action1", "tool": "browser_type", "ok": True, "bytes": 200, "t_mono_ns": t(25)},
          {"event": "oracle_send", "label": "o2", "t_mono_ns": t(25.2)},
          {"event": "oracle_return", "label": "o2", "outcome": "unknown", "t_mono_ns": t(25.4)},
          {"event": "call_send", "label": "snapshot2", "tool": "get_browser_state", "snapshot_format": "semantic_v2",
           "has_query": False, "t_mono_ns": t(25.4)},
          {"event": "call_return", "label": "snapshot2", "tool": "get_browser_state", "ok": True, "bytes": 3100,
           "n_refs": 2, "t_mono_ns": t(33)},
          {"event": "cand_start", "t_mono_ns": t(33)}, {"event": "cand_done", "t_mono_ns": t(34)}]
    if arm == "D":
        ev += [{"event": "guard_start", "t_mono_ns": t(34)},
               {"event": "guard_done", "status": guard, "reason": None if guard == "accepted" else "submit_not_unique",
                "t_mono_ns": t(34.5 if guard != "accepted" else 35)}]
        if guard != "accepted":
            ev += [{"event": "decide_start", "t_mono_ns": t(34.5)}, {"event": "decided", "choice": "submit-form", "t_mono_ns": t(35)}]
    else:
        ev += [{"event": "decide_start", "t_mono_ns": t(34)}, {"event": "decided", "choice": "submit-form", "t_mono_ns": t(35)}]
    ev += [{"event": "call_send", "label": "action2", "tool": "browser_click", "t_mono_ns": t(35)},
           {"event": "call_return", "label": "action2", "tool": "browser_click", "ok": True, "bytes": 250, "t_mono_ns": t(50)},
           {"event": "oracle_send", "label": "v0", "t_mono_ns": t(52)},
           {"event": "oracle_return", "label": "v0", "outcome": outcome, "t_mono_ns": t(53)},
           {"event": "stdio_close_start", "t_mono_ns": t(60)},
           {"event": "resource_sample_start", "t_mono_ns": t(60)}, {"event": "resource_sample_end", "t_mono_ns": t(61)},
           {"event": "stdio_closed", "t_mono_ns": t(80)}, {"event": "browser_gone", "t_mono_ns": t(300)}]
    trace = [
        {"phase": "mcp.line_read", "t_mono_ns": t(0.5)}, {"phase": "dispatch.enter", "t_mono_ns": t(1)},
        {"phase": "snap.enter", "t_mono_ns": t(1.5)}, {"phase": "snap.collected", "t_mono_ns": t(8)},
        {"phase": "dispatch.exit", "t_mono_ns": t(9)}, {"phase": "mcp.written", "t_mono_ns": t(9.5)},
        {"phase": "type.enter", "t_mono_ns": t(14)}, {"phase": "focus.settle_start", "t_mono_ns": t(15),
                                                      "detail": {"settle_ms": settle}},
        {"phase": "focus.settle_end", "t_mono_ns": t(22)}, {"phase": "type.insert_send", "t_mono_ns": t(22)},
        {"phase": "type.insert_response", "t_mono_ns": t(23)}, {"phase": "mcp.written", "t_mono_ns": t(24.5)},
        {"phase": "snap.enter", "t_mono_ns": t(26)}, {"phase": "snap.collected", "t_mono_ns": t(31)},
        {"phase": "mcp.written", "t_mono_ns": t(32.5)},
        {"phase": "click.enter", "t_mono_ns": t(36)}, {"phase": "reval.native_window", "t_mono_ns": t(37)},
        {"phase": "click.ref_resolved", "t_mono_ns": t(44)}, {"phase": "click.cdp_send", "t_mono_ns": t(46)},
        {"phase": "click.cdp_response", "t_mono_ns": t(47)}, {"phase": "mcp.written", "t_mono_ns": t(49.5)},
        {"phase": "platform.gate", "t_mono_ns": t(36.5), "detail": {"cursor_enabled": False}},
    ]
    if cursor_marks:
        trace.append({"phase": "overlay.arrival_wait_end", "t_mono_ns": t(40), "detail": {"arrived": True}})
    if ledger:
        for k, (a, b) in enumerate(((2, 3), (3, 4), (4, 6), (27, 28), (28, 30))):
            trace.append({"phase": "cdp.send", "t_mono_ns": t(a), "detail": {"id": k, "method":
                          ["Target.attachToTarget", "DOM.getDocument", "DOMSnapshot.captureSnapshot",
                           "DOM.getDocument", "DOMSnapshot.captureSnapshot"][k], "on_session": True, "bytes": 100}})
            trace.append({"phase": "cdp.reply", "t_mono_ns": t(b), "detail": {"id": k, "bytes": 5000, "error": False}})
        trace += [{"phase": "cdp.event", "t_mono_ns": t(29), "detail": {"method": "DOM.attributeModified", "on_session": True, "bytes": 90}},
                  {"phase": "snap.acquired_dom", "t_mono_ns": t(7), "detail": {"dom_nodes": 40, "layout_nodes": 30}},
                  {"phase": "snap.acquired_ax", "t_mono_ns": t(7.5), "detail": {"ax_nodes": 25}},
                  {"phase": "snap.acquired_dom", "t_mono_ns": t(30.5), "detail": {"dom_nodes": 41, "layout_nodes": 31}},
                  {"phase": "snap.acquired_ax", "t_mono_ns": t(30.7), "detail": {"ax_nodes": 26}}]
    trace.sort(key=lambda m: m["t_mono_ns"])
    journal = [{"event": "config", "t_mono_ns": t0 - 900 * MS}]
    journal += [{"event": "submit", "endpoint": "/submit", "t_mono_ns": t(49) + i, "received_t_mono_ns": t(49)}
                for i in range(submits)]
    journal += [{"event": "wrong_target_submit", "endpoint": "/submit-decoy", "t_mono_ns": t(49)} for _ in range(wrong)]
    routes = ["provider", "guarded-completion"] if (arm == "D" and guard == "accepted") else ["provider", "provider"]
    runlog = [{"event": "step", "step": 1, "candidate": "type-verification-value", "decision_route": "provider",
               "tool": "browser_type"},
              {"event": "step", "step": 2, "candidate": "submit-form", "decision_route": routes[1], "tool": "browser_click",
               **({"guarded_completion": {"status": guard} if guard == "accepted" else
                   {"status": "declined", "reason": "submit_not_unique"}} if arm == "D" else {})},
              {"event": "outcome", "outcome": outcome}]
    summary = {"trial": f"x-{arm}", "arm": arm, "pair": pair, "condition": condition, "comparison": "CMP-D",
               "cohort": "K1", "kind": "control" if control else "measured", "control": control, "excluded": None,
               "outcome": outcome, "token_sha16": "abc", "final_state": {"submitted_sha16": "abc" if submits else None},
               "poller_first_ok_ns": None if poller_ms is None else t(poller_ms), "journal": journal,
               "loadavg_before": f"{load1} 1.0 1.0 1/100 1", "cursor_ack": {"requested": False, "ok": True},
               "resources": {"driver_cpu_s": 0.5, "driver_vmhwm_kib": 50000, "browser_cpu_s": 2.0, "browser_rss_kib": 400000}}
    return {"name": summary["trial"], "summary": summary, "events": ev, "trace": trace, "runlog": runlog}


class DecomposeTest(unittest.TestCase):
    def test_ledger_marks_do_not_change_the_decomposition(self) -> None:
        a = D.decompose_d(synth(ledger=True))
        b = D.decompose_d(synth(ledger=False))
        self.assertEqual(a["components"], b["components"])
        self.assertAlmostEqual(a["coverage"], b["coverage"])

    def test_oracle_end_and_components_sum_to_T(self) -> None:
        r = D.decompose_d(synth(poller_ms=49.5))
        self.assertAlmostEqual(r["T_ms"], 49.5)
        self.assertAlmostEqual(sum(r["components"].values()), 49.5, places=6)
        self.assertAlmostEqual(sum(r["spans10"].values()), 49.5, places=6)
        self.assertEqual(r["end"], "oracle")

    def test_runner_end_is_available(self) -> None:
        r = D.decompose_d(synth(), end="runner")
        self.assertAlmostEqual(r["T_ms"], 53.0)

    def test_guard_plan_and_candidate_build_are_named(self) -> None:
        r = D.decompose_d(synth("D"), end="runner")
        self.assertAlmostEqual(r["components"]["guard_program"], 2.0, places=6)  # plan 1 + guard 1
        self.assertAlmostEqual(r["components"]["candidate_build"], 2.0, places=6)
        self.assertAlmostEqual(r["components"]["decision"], 1.0, places=6)
        a = D.decompose_d(synth("A"), end="runner")
        self.assertAlmostEqual(a["components"]["decision"], 2.0, places=6)
        self.assertAlmostEqual(a["components"]["guard_program"], 0.0, places=6)  # run.py never plans without the flag

    def test_spans10_mapping(self) -> None:
        r = D.decompose_d(synth("D"), end="runner")
        s, c = r["spans10"], r["components"]
        self.assertAlmostEqual(s["provider_inference"], c["decision"])
        self.assertAlmostEqual(s["resolution_validation"], c["resolution"] + c["revalidate"] + c["driver_pre_dispatch"]
                               + c["input_prep"] + c["guard_program"])
        self.assertAlmostEqual(s["observation_acquisition"], r["sub"].get("observation_cdp", 0.0))
        self.assertEqual(set(s), set(D.SPANS10))
        self.assertGreater(r["coverage"], 0.9)

    def test_undefined_without_snapshot_or_oracle(self) -> None:
        self.assertIsNone(D.decompose_d(synth(poller_ms=None)))

    def test_cleanup_and_lifetime(self) -> None:
        c = D.cleanup_spans(synth())
        self.assertAlmostEqual(c["session_close_ms"], 20.0)
        self.assertAlmostEqual(c["resource_sample_ms"], 1.0)
        self.assertAlmostEqual(c["browser_exit_ms"], 220.0)
        self.assertAlmostEqual(c["cleanup_ms"], 240.0)
        self.assertAlmostEqual(c["lifetime_ms"], 800.0)
        self.assertAlmostEqual(c["cold_startup_ms"], 450.0)


class CountsTest(unittest.TestCase):
    def test_counts_from_ledger_runlog_and_journal(self) -> None:
        c = D.counts(synth("D"))
        self.assertEqual(c["snapshots_full"], 2)
        self.assertEqual(c["snapshots_query"], 0)
        self.assertEqual(c["cdp_sends_by_method"]["DOM.getDocument"], 2)
        self.assertEqual(c["cdp_sends"], 5)
        self.assertEqual(c["cdp_send_bytes"], 500)
        self.assertEqual(c["cdp_reply_bytes"], 25000)
        self.assertEqual(c["cdp_events_by_method"], {"DOM.attributeModified": 1})
        self.assertEqual((c["acquired_dom_nodes"], c["acquired_layout_nodes"], c["acquired_ax_nodes"]), (81, 61, 51))
        self.assertEqual(c["decisions"], 1)
        self.assertEqual(c["plan_calls"], 1)
        self.assertEqual(c["resolve_calls"], 1)
        self.assertEqual(c["guard"], [{"status": "accepted", "reason": None}])
        self.assertEqual(c["decision_routes"], ["provider", "guarded-completion"])
        self.assertEqual(c["driver_mutations"], 2)
        self.assertEqual(c["journal_submits"], 1)
        self.assertEqual(c["mcp_snapshot_bytes"], 6100)
        self.assertEqual(c["refs_returned"], [2, 2])
        self.assertEqual(D.counts(synth("A"))["decisions"], 2)


class ValidityTest(unittest.TestCase):
    def test_forced_paths(self) -> None:
        self.assertEqual(D.validity(synth("A")), [])
        self.assertEqual(D.validity(synth("D")), [])
        self.assertIn("routes=['provider', 'provider']", D.validity(synth("D", guard="declined")))
        self.assertIn("feedback_not_off", D.validity(synth("A", cursor_marks=True)))
        self.assertIn("settle=[0]", D.validity(synth("A", settle=0)))
        self.assertIn("journal_submits=2", D.validity(synth("A", submits=2)))
        self.assertIn("wrong_target=1", D.validity(synth("A", wrong=1)))
        self.assertIn("T_undefined", D.validity(synth("A", poller_ms=None)))
        bad = synth("A")
        bad["summary"]["excluded"] = "shakedown"
        self.assertIn("excluded=shakedown", D.validity(bad))


class StatsAndDecisionTest(unittest.TestCase):
    def test_verdict_thresholds(self) -> None:
        self.assertEqual(D.verdict([-10.0] * 30, 100.0)["verdict"], "MEANINGFUL")
        self.assertEqual(D.verdict([0.1 * ((-1) ** i) for i in range(30)], 100.0)["verdict"], "NO_MEANINGFUL_BENEFIT")
        wide = [(-12.0 if i % 2 else 9.0) for i in range(30)]
        self.assertEqual(D.verdict(wide, 100.0)["verdict"], "INCONCLUSIVE")
        self.assertEqual(D.verdict([-1.0] * 30, 400.0)["threshold_ms"], 20.0)
        self.assertEqual(D.verdict([-1.0] * 30, 40.0)["threshold_ms"], 5.0)
        self.assertEqual(D.verdict([], 40.0)["verdict"], "NO_DATA")

    def test_continuation_rule(self) -> None:
        self.assertTrue(D.continuation_needed({"verdict": "INCONCLUSIVE", "n": 30}))
        self.assertFalse(D.continuation_needed({"verdict": "INCONCLUSIVE", "n": 60}))
        self.assertFalse(D.continuation_needed({"verdict": "MEANINGFUL", "n": 30}))

    def test_paired_analysis_uses_complete_valid_pairs_only(self) -> None:
        trials = []
        for p in range(3):
            a, d = synth("A", pair=f"p{p}", poller_ms=60.0), synth("D", pair=f"p{p}", poller_ms=58.0)
            trials += [a, d]
        trials[1]["summary"]["outcome"] = "unknown"  # pair p0 D invalid
        res = D.paired(trials, "CMP-D", "W-quiet")
        self.assertEqual(res["pairs_seen"], 3)
        self.assertEqual(res["pairs_valid"], 2)
        self.assertEqual(res["deltas_ms"], [-2.0, -2.0])
        self.assertEqual(res["excluded_pairs"][0]["pair"], "p0")

    def test_required_zero_counts(self) -> None:
        z = D.required_zero([synth("D", submits=2), synth("D", wrong=1, control="DC06"), synth("A")])
        self.assertEqual(z["D"]["duplicate_effect"], 1)
        self.assertEqual(z["D"]["wrong_target_effect"], 1)
        self.assertEqual(z["A"]["duplicate_effect"], 0)
        u = synth("A", outcome="verified", submits=0, poller_ms=None)
        self.assertEqual(D.required_zero([u])["A"]["unverified_success"], 1)

    def test_disposition(self) -> None:
        self.assertEqual(D.disposition(None, {"D": {"wrong_target_effect": 0}}, decisions_deleted=None)["disposition"],
                         "BLOCKED")
        z_bad = {"D": {"wrong_target_effect": 1, "duplicate_effect": 0, "unverified_success": 0,
                       "stale_ref_effect": 0, "unauthorized_action": 0}}
        self.assertTrue(D.disposition({"W-quiet": {"verdict": "MEANINGFUL"}, "W-churn": {"verdict": "MEANINGFUL"}},
                                      z_bad, decisions_deleted=1.0)["disposition"].startswith("REVISE"))
        z_ok = {"D": {k: 0 for k in z_bad["D"]}}
        self.assertTrue(D.disposition({"W-quiet": {"verdict": "NO_MEANINGFUL_BENEFIT"}, "W-churn": {"verdict": "INCONCLUSIVE"}},
                                      z_ok, decisions_deleted=1.0)["disposition"].startswith("REPORT_WORK_DELETED"))
        self.assertTrue(D.disposition({"W-quiet": {"verdict": "MEANINGFUL"}, "W-churn": {"verdict": "MEANINGFUL"}},
                                      z_ok, decisions_deleted=1.0)["disposition"].startswith("PRIORITIZE"))


if __name__ == "__main__":
    unittest.main()
