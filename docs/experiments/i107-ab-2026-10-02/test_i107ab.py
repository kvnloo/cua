"""Unit tests for the kvnloo/cua#107 lane AB harness pieces (no Driver, no browser).

    JEV_USE_DIR=<jev-use> <jev-use>/.venv/bin/python -m unittest test_i107ab -v
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import b01_analysis as A  # noqa: E402
import i107ab_fixtures as F  # noqa: E402
import i107ab_ledger as L  # noqa: E402


def mark(t: int, phase: str, **detail: object) -> dict:
    return {"t_mono_ns": t, "seq": t, "phase": phase, "session": "", "detail": detail or None}


def ev(t: int, name: str, **fields: object) -> dict:
    return {"event": name, "t_mono_ns": t, **fields}


SNAP_WINDOW_TRACE = [
    mark(100, "snap.enter"),
    mark(110, "cdp.send", id=1, method="Target.attachToTarget", on_session=False, bytes=80),
    mark(120, "cdp.reply", id=1, bytes=60, error=False),
    mark(121, "snap.attached"),
    mark(130, "cdp.send", id=2, method="DOM.getDocument", on_session=True, bytes=90),
    mark(140, "cdp.event", method="DOM.attributeModified", on_session=True, bytes=70),
    mark(150, "cdp.reply", id=2, bytes=5000, error=False),
    mark(151, "snap.document"),
    mark(160, "cdp.send", id=3, method="DOMSnapshot.captureSnapshot", on_session=True, bytes=120),
    mark(161, "cdp.send", id=4, method="Page.getLayoutMetrics", on_session=True, bytes=70),
    mark(170, "cdp.reply", id=4, bytes=300, error=False),
    mark(180, "cdp.reply", id=3, bytes=9000, error=False),
    mark(181, "snap.layout_cdp_done"),
    mark(182, "snap.indexed"),
    mark(183, "snap.acquired_dom", dom_nodes=40, layout_nodes=30),
    mark(190, "cdp.send", id=5, method="Accessibility.getFullAXTree", on_session=True, bytes=100),
    mark(200, "cdp.reply", id=5, bytes=7000, error=False),
    mark(201, "snap.ax_cdp_done"),
    mark(202, "snap.acquired_ax", ax_nodes=25),
    mark(210, "snap.paged"),
]


class LedgerTests(unittest.TestCase):
    def test_window_ledger_counts_methods_bytes_and_nodes(self) -> None:
        led = L.ledger_for_window(SNAP_WINDOW_TRACE, 90, 220)
        self.assertEqual(led["methods"], {"Target.attachToTarget": 1, "DOM.getDocument": 1,
                                          "DOMSnapshot.captureSnapshot": 1, "Page.getLayoutMetrics": 1,
                                          "Accessibility.getFullAXTree": 1})
        self.assertEqual(led["send_bytes"], 80 + 90 + 120 + 70 + 100)
        self.assertEqual(led["reply_bytes"], 60 + 5000 + 300 + 9000 + 7000)
        self.assertEqual(led["reply_bytes_by_method"]["DOMSnapshot.captureSnapshot"], 9000)
        self.assertEqual(led["events"], {"DOM.attributeModified": 1})
        self.assertEqual(led["event_bytes"], 70)
        self.assertEqual((led["dom_nodes"], led["layout_nodes"], led["ax_nodes"]), (40, 30, 25))
        self.assertEqual(led["unmatched_replies"], 0)
        self.assertEqual(led["reply_errors"], 0)

    def test_window_bounds_exclude_outside_marks(self) -> None:
        led = L.ledger_for_window(SNAP_WINDOW_TRACE, 155, 185)
        self.assertEqual(led["methods"], {"DOMSnapshot.captureSnapshot": 1, "Page.getLayoutMetrics": 1})
        self.assertEqual(led["dom_nodes"], 40)
        self.assertEqual(led["ax_nodes"], 0)

    def test_strip_ledger_marks_keeps_phase_marks_only(self) -> None:
        phases = [m["phase"] for m in L.strip_ledger(SNAP_WINDOW_TRACE)]
        self.assertNotIn("cdp.send", phases)
        self.assertNotIn("snap.acquired_dom", phases)
        self.assertEqual(phases[0], "snap.enter")
        self.assertIn("snap.indexed", phases)

    def test_snapshot_ledgers_follow_caller_call_windows(self) -> None:
        events = [ev(90, "call_send", label="snapshot1", tool="get_browser_state"),
                  ev(220, "call_return", label="snapshot1", tool="get_browser_state", ok=True)]
        trial = {"events": events, "trace": SNAP_WINDOW_TRACE, "summary": {}}
        snaps = L.snapshot_ledgers(trial)
        self.assertEqual([s["label"] for s in snaps], ["snapshot1"])
        self.assertEqual(snaps[0]["methods"]["DOM.getDocument"], 1)

    def test_compare_acquisition_exact_and_differences(self) -> None:
        a = [L.ledger_for_window(SNAP_WINDOW_TRACE, 90, 220)]
        b = [L.ledger_for_window(SNAP_WINDOW_TRACE, 90, 220)]
        res = L.compare_acquisition(a, b)
        self.assertTrue(res["methods_equal"])
        self.assertTrue(res["nodes_equal"])
        b2 = [dict(b[0], methods=Counter(b[0]["methods"]) - Counter({"Accessibility.getFullAXTree": 1}),
                   ax_nodes=0)]
        res2 = L.compare_acquisition(a, b2)
        self.assertFalse(res2["methods_equal"])
        self.assertFalse(res2["nodes_equal"])
        self.assertTrue(res2["diffs"])
        res3 = L.compare_acquisition(a, a + a)
        self.assertFalse(res3["steps_equal"])


class DecompositionTests(unittest.TestCase):
    def test_ledger_marks_do_not_split_phase_intervals(self) -> None:
        events = [ev(90, "call_send", label="snapshot1", tool="get_browser_state"),
                  ev(220, "call_return", label="snapshot1", tool="get_browser_state", ok=True),
                  ev(230, "oracle_send", label="verify0"), ev(240, "oracle_return", label="verify0", outcome="verified")]
        trial = {"summary": {"cls": "fill", "journal": [], "poller_first_ok_ns": 250},
                 "events": events, "trace": SNAP_WINDOW_TRACE}
        d = A.decompose(L.decomposable(trial))
        self.assertIsNotNone(d)
        self.assertEqual(d["unknown_marks"], {})
        self.assertAlmostEqual(d["components"]["unattributed"], 0.0)
        # snap.indexed -> snap.ax_cdp_done (with the acquired_dom point removed) is CDP acquisition.
        self.assertGreater(d["sub"]["observation_cdp"], 0)

    def test_span10_mapping_is_complete_and_additive(self) -> None:
        comp = {c: 1.0 for c in A.COMPONENTS}
        comp.update({"client_parse": 1.0, "candidate_build": 1.0})
        spans = L.span10(comp, sub={"observation_cdp": 0.6, "observation_processing": 0.4})
        self.assertEqual(set(spans), set(L.SPANS10))
        self.assertAlmostEqual(sum(spans.values()), sum(comp.values()))
        self.assertAlmostEqual(spans["observation acquisition"], 0.6)
        self.assertAlmostEqual(spans["residual/unattributed"], 2.0)

    def test_classify_new_projection_marks(self) -> None:
        self.assertEqual(A.classify_mark("mcp.handled", "get_browser_state"), ("driver_post_dispatch", "driver_serialize"))
        self.assertEqual(A.classify_mark("mcp.serialized", "get_browser_state"), ("driver_post_dispatch", "driver_write"))
        self.assertEqual(A.classify_mark("snap.oopif_done", "get_browser_state"), ("observation", "projection_page"))


class FixtureTests(unittest.TestCase):
    def test_quiet_page_is_jev_use_page_byte_for_byte(self) -> None:
        import fixture_server
        self.assertEqual(F.page_for("W-quiet", seed=1, control=False), fixture_server.PAGE)

    def test_churn_region_has_500_nodes_and_no_query_words(self) -> None:
        page = F.page_for("W-churn", seed=20261002, control=False).decode()
        region = page[page.index('<section id="i107-churn"'):page.index("</section>") + len("</section>")]
        n = len(re.findall(r"<(div|span|p|li|em)\b", region))
        self.assertEqual(n, 500)
        visible = re.sub(r"<script.*?</script>", "", region, flags=re.S).lower()
        for word in ("submit", "verification", "value"):
            self.assertNotIn(word, visible)
        for word in F.VOCAB:
            for bad in ("submit", "verification", "value"):
                self.assertNotIn(bad, word.lower())

    def test_churn_keeps_form_subtree_byte_identical(self) -> None:
        import fixture_server
        quiet = fixture_server.PAGE.decode()
        form = quiet[quiet.index("<form"):quiet.index("</form>") + len("</form>")]
        for cond in ("W-churn", "W-static"):
            page = F.page_for(cond, seed=7, control=True).decode()
            self.assertEqual(page[page.index("<form"):page.index("</form>") + len("</form>")], form)

    def test_churn_is_seeded_and_static_never_starts_interval(self) -> None:
        a = F.page_for("W-churn", seed=11, control=False)
        self.assertEqual(a, F.page_for("W-churn", seed=11, control=False))
        self.assertNotEqual(a, F.page_for("W-churn", seed=12, control=False))
        churn_js = F.churn_script(seed=11, run=True)
        static_js = F.churn_script(seed=11, run=False)
        self.assertIn("setInterval", churn_js)
        self.assertIn("50", churn_js)  # 20 Hz
        self.assertNotIn("setInterval", static_js)
        self.assertIn("i107-churn", F.page_for("W-static", seed=11, control=False).decode())

    def test_control_script_only_on_control_trials(self) -> None:
        self.assertNotIn(b"EventSource", F.page_for("W-quiet", seed=1, control=False))
        self.assertIn(b"EventSource", F.page_for("W-quiet", seed=1, control=True))

    def test_control_ops_are_defined_for_dc03_and_dc04(self) -> None:
        self.assertIn("dc_submitter", F.CONTROL_OPS["DC03"])
        self.assertIn("insertBefore", F.CONTROL_OPS["DC03"])
        self.assertIn("remove()", F.CONTROL_OPS["DC04"])

    def test_journal_records_submitter_and_wrong_target(self) -> None:
        st = F.JournalFormState()
        st.submit_form("tok", submitter="competitor")
        st.submit_form("tok", submitter=None)
        j = st.drain()
        self.assertEqual([e["submitter"] for e in j], ["competitor", "original"])
        self.assertEqual(F.wrong_target_submits(j), 1)
        self.assertNotIn("tok", json.dumps(j))  # token never journaled in clear

    def test_control_bus_ack_roundtrip(self) -> None:
        bus = F.ControlBus()
        op_id = bus.post("DC04")
        self.assertEqual(bus.next_op(timeout=0.1)["op"], "DC04")
        bus.ack(op_id)
        self.assertTrue(bus.wait_ack(op_id, timeout=0.1))
        self.assertFalse(bus.wait_ack("missing", timeout=0.01))
        kinds = [e["event"] for e in bus.journal]
        self.assertEqual(kinds, ["control_post", "control_ack"])


class SemanticEquivalenceTests(unittest.TestCase):
    SNAP = {"refs": [
        {"ref": "r1", "role": "textbox", "name": "verification value", "value": "zq-secret-91", "states": {"focused": True},
         "actions": ["type"], "frame": "main", "visibility": "in_viewport"},
        {"ref": "r2", "role": "button", "name": "Submit", "value": None, "states": {}, "actions": ["click"],
         "frame": "main", "visibility": "in_viewport"}],
        "content_refs": [{"ref": "c1"}], "snapshot": {"selected_nodes": 9, "total_nodes": 9, "scope": "viewport"}}

    def test_logical_controls_hide_the_token(self) -> None:
        sig = L.logical_controls(self.SNAP, "zq-secret-91")
        self.assertEqual(sig["textbox:verification value"]["value_is_token"], True)
        self.assertEqual(sig["button:Submit"]["count"], 1)
        self.assertNotIn("zq-secret-91", json.dumps(sig))
        self.assertNotIn("r1", json.dumps(sig))

    def test_equivalence_detects_missing_submit_and_candidate_drift(self) -> None:
        a = [{"candidates": ["type-verification-value", "reobserve", "abstain"], "controls": L.logical_controls(self.SNAP, "zq-secret-91")}]
        self.assertTrue(L.equivalent(a, a)["equivalent"])
        snap2 = {**self.SNAP, "refs": self.SNAP["refs"][:1]}
        b = [{"candidates": ["type-verification-value", "reobserve", "abstain"], "controls": L.logical_controls(snap2, "zq-secret-91")}]
        res = L.equivalent(a, b)
        self.assertFalse(res["equivalent"])
        self.assertTrue(any("button:Submit" in r for r in res["reasons"]))
        c = [{"candidates": ["reobserve", "abstain"], "controls": a[0]["controls"]}]
        self.assertFalse(L.equivalent(a, c)["equivalent"])


class ProcTests(unittest.TestCase):
    def make_proc(self, root: Path, procs: dict[int, tuple[int, int, int, int, int]]) -> None:
        # pid -> (ppid, utime, stime, VmHWM kB, VmRSS kB)
        for pid, (ppid, ut, stt, hwm, rss) in procs.items():
            d = root / str(pid)
            d.mkdir()
            fields = ["S", str(ppid)] + ["0"] * 9 + [str(ut), str(stt)] + ["0"] * 20
            (d / "stat").write_text(f"{pid} (my (odd) name) " + " ".join(fields) + "\n")
            (d / "status").write_text(f"Name:\tx\nVmHWM:\t{hwm} kB\nVmRSS:\t{rss} kB\n")
            (d / "cmdline").write_bytes(b"/bin/x\x00mcp\x00")
        (root / "self").mkdir()

    def test_stat_status_and_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_proc(root, {10: (1, 5, 6, 100, 90), 11: (10, 1, 1, 50, 40), 12: (11, 2, 2, 30, 20), 13: (1, 9, 9, 1, 1)})
            self.assertEqual(L.cpu_ticks(10, proc=root), 11)
            self.assertEqual(L.status_kb(10, proc=root), {"VmHWM": 100, "VmRSS": 90})
            self.assertEqual(L.descendants(10, proc=root), {11, 12})
            tree = L.tree_usage(10, proc=root)
            self.assertEqual(tree, {"pids": 3, "cpu_ticks": 11 + 2 + 4, "rss_kb": 90 + 40 + 20})
            self.assertEqual(L.children_with_argv0(1, "/bin/x", proc=root), [10, 13])
            self.assertIsNone(L.cpu_ticks(99, proc=root))

    def test_psi_and_loadavg_readers_never_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = L.pressure(proc=Path(tmp))
            self.assertEqual(out, {"cpu": "unavailable", "memory": "unavailable"})


class PreflightTests(unittest.TestCase):
    def test_trust_precondition_mirrors_driver_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "chrome"
            exe.write_text("#!/bin/sh\n")
            exe.chmod(0o755)
            res = L.trust_precondition([str(exe)])
            # A file owned by this (non-root) user can never satisfy the Driver's rule.
            self.assertFalse(res["ok"])
            self.assertEqual(res["checked"][0]["reason"], "uid_not_0")
            missing = L.trust_precondition([str(Path(tmp) / "absent")])
            self.assertEqual(missing["checked"][0]["reason"], "missing")
            self.assertFalse(L.trust_precondition(["relative/chrome"])["ok"])

    def test_candidate_list_matches_driver(self) -> None:
        self.assertEqual(L.DRIVER_ISOLATED_CANDIDATES, (
            "/opt/google/chrome/google-chrome", "/usr/lib/chromium/chromium",
            "/usr/lib/chromium-browser/chromium-browser", "/opt/microsoft/msedge/msedge"))


class StatsAndPlanTests(unittest.TestCase):
    def test_improvement_verdicts(self) -> None:
        self.assertEqual(L.improvement_verdict(-10.0, [-15.0, -6.0], 5.0), "meaningful")
        self.assertEqual(L.improvement_verdict(-1.0, [-3.0, 2.0], 5.0), "no_meaningful_benefit")
        self.assertEqual(L.improvement_verdict(-4.0, [-9.0, 1.0], 5.0), "inconclusive")
        self.assertEqual(L.threshold_ms(80.0), 5.0)
        self.assertEqual(L.threshold_ms(200.0), 10.0)

    def test_within_noise_rule(self) -> None:
        self.assertTrue(L.within_noise([1.0, -1.0, 0.0, 2.0, -2.0], a_median=1000.0, rel=0.02)["equal"])
        self.assertFalse(L.within_noise([50.0] * 10, a_median=1000.0, rel=0.02)["equal"])

    def test_denominators(self) -> None:
        d = L.denominators(["verified", "verified", "timeout", "weird", "abstained"])
        self.assertEqual(d["verified"], 2)
        self.assertEqual(d["timeout"], 1)
        self.assertEqual(d["other"], 1)
        self.assertEqual(d["n"], 5)

    def test_abba_plan(self) -> None:
        plan = L.abba_pairs("A", "B_proj", 4)
        self.assertEqual(plan, [("A", "B_proj"), ("B_proj", "A"), ("B_proj", "A"), ("A", "B_proj")])

    def test_pairs_from_trials(self) -> None:
        rows = [{"pair": "p0", "arm": "A", "x": 10.0}, {"pair": "p0", "arm": "B_proj", "x": 7.0},
                {"pair": "p1", "arm": "A", "x": 10.0}]
        self.assertEqual(L.paired_values(rows, "A", "B_proj", "x"), ([10.0], [7.0]))


class WireTests(unittest.TestCase):
    def test_wire_recorder_counts_bytes_and_times_parse(self) -> None:
        rec = []
        parse = L.recording_parser(lambda line: {"parsed": len(line)}, lambda **f: rec.append(f))
        out = parse('{"jsonrpc":"2.0","id":3,"result":{}}')
        self.assertEqual(out, {"parsed": 36})
        self.assertEqual(rec[0]["bytes"], 36)
        self.assertLessEqual(rec[0]["t0"], rec[0]["t1"])


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import run_critpath as R
        cls.R = R

    def test_query_and_arms(self) -> None:
        R = self.R
        self.assertEqual(R.QUERY, "verification value submit")
        self.assertEqual((R.ARMS["A"].query, R.ARMS["A"].trace, R.ARMS["A"].binary), (None, True, "i107"))
        self.assertEqual((R.ARMS["B_proj"].query, R.ARMS["B_proj"].binary), ("verification value submit", "i107"))
        self.assertEqual((R.ARMS["A_ref"].binary, R.ARMS["A_ref"].trace), ("ref", False))
        self.assertEqual((R.ARMS["A_off"].binary, R.ARMS["A_off"].trace), ("i107", False))

    def test_ab_plan_is_abba_blocked_by_condition(self) -> None:
        plan = self.R.build_plan("ab", 30, ["W-quiet", "W-churn"])
        self.assertEqual(len(plan), 120)
        self.assertEqual(len({t["name"] for t in plan}), 120)
        self.assertEqual(len({t["seed"] for t in plan}), 120)
        self.assertEqual([t["condition"] for t in plan[:60]], ["W-quiet"] * 60)
        pairs: dict[str, list[str]] = {}
        for t in plan:
            pairs.setdefault(t["pair"], []).append(t["arm"])
        self.assertEqual(len(pairs), 60)
        self.assertTrue(all(sorted(v) == ["A", "B_proj"] for v in pairs.values()))
        self.assertEqual([plan[i]["arm"] for i in range(8)], ["A", "B_proj", "B_proj", "A", "B_proj", "A", "A", "B_proj"])
        self.assertFalse(any(t["excluded"] for t in plan))

    def test_other_plans(self) -> None:
        R = self.R
        self.assertEqual([t["arm"] for t in R.build_plan("default_off", 30, [])], ["A_off"] * 5)
        dist = R.build_plan("distortion", 30, [])
        self.assertEqual(len(dist), 20)
        self.assertEqual(Counter(t["arm"] for t in dist), {"A": 10, "A_ref": 10})
        ctl = R.build_plan("controls", 30, [])
        self.assertEqual(Counter((t["control"], t["arm"]) for t in ctl)[("DC03", "B_proj")], 5)
        self.assertEqual(len(ctl), 30)
        self.assertTrue(all(t["excluded"] for t in R.build_plan("shakedown", 30, [])))
        st = R.build_plan("static", 30, ["W-quiet", "W-churn"])
        self.assertEqual({t["condition"] for t in st}, {"W-static"})
        self.assertEqual(len(st), 60)

    def test_snapshot_facts_never_carry_token_or_refs(self) -> None:
        snap = {**SemanticEquivalenceTests.SNAP, "outline": "x" * 10}
        facts = self.R.snapshot_facts(snap, "zq-secret-91")
        text = json.dumps(facts)
        self.assertNotIn("zq-secret-91", text)
        self.assertNotIn('"r1"', text)
        self.assertEqual(facts["refs"], 2)
        self.assertEqual(facts["outline_chars"], 10)

    def test_stdio_reader_parse_is_recorded(self) -> None:
        R = self.R
        rec = R.Recorder()
        R.CLIENT["rec"] = rec
        try:
            msg = R._mcp_stdio.types.JSONRPCMessage.model_validate_json('{"jsonrpc":"2.0","id":1,"result":{}}')
        finally:
            R.CLIENT["rec"] = None
        self.assertEqual(type(msg).__name__, "JSONRPCMessage")
        self.assertEqual([e["event"] for e in rec.events], ["parse_start", "parse_end"])
        self.assertEqual(rec.events[1]["bytes"], 36)
        self.assertIs(R._mcp_stdio.types.CallToolResult, R._mcp_types.CallToolResult)


class FixtureServerLoopbackTests(unittest.TestCase):
    def setUp(self) -> None:
        import threading
        self.srv = F.I107Server(("127.0.0.1", 0))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self) -> None:
        self.srv.stopping = True
        self.srv.shutdown()
        self.srv.server_close()

    def _post(self, path: str, body: bytes) -> int:
        from urllib.request import Request, urlopen
        with urlopen(Request(self.base + path, data=body, method="POST"), timeout=2) as r:
            return r.status

    def test_pages_submit_journal_and_oracle(self) -> None:
        from urllib.request import urlopen
        import fixture_server
        self.srv.configure("W-quiet", 1, False)
        self.assertEqual(urlopen(self.base + "/", timeout=2).read(), fixture_server.PAGE)
        self.srv.configure("W-churn", 5, False)
        self.assertIn(b"i107-churn", urlopen(self.base + "/", timeout=2).read())
        self.assertEqual(self._post("/submit", b"value=abc&dc_submitter=competitor"), 200)
        state = json.loads(urlopen(self.base + "/state", timeout=2).read())
        self.assertEqual(state, {"submitted": "abc", "submitter": "competitor"})
        self.assertEqual(self._post("/reset", b""), 204)
        journal = self.srv.state.drain()
        self.assertEqual([e["event"] for e in journal], ["submit", "reset"])
        self.assertEqual(F.wrong_target_submits(journal), 1)

    def test_event_stream_delivers_one_op_and_ack_is_journaled(self) -> None:
        import threading
        from urllib.request import urlopen
        self.srv.configure("W-quiet", 1, True)
        got: list[dict] = []

        def client() -> None:
            with urlopen(self.base + "/events", timeout=3) as stream:
                for raw in stream:
                    line = raw.decode().strip()
                    if line.startswith("data: "):
                        op = json.loads(line[6:])
                        got.append(op)
                        self._post("/ack", op["id"].encode())
                        return

        th = threading.Thread(target=client, daemon=True)
        th.start()
        import time as _t
        deadline = _t.monotonic() + 2
        while self.srv.bus.latest_conn == 0 and _t.monotonic() < deadline:
            _t.sleep(0.01)
        op_id = self.srv.bus.post("DC04")
        self.assertTrue(self.srv.bus.wait_ack(op_id, 2.0))
        th.join(timeout=2)
        self.assertEqual(got[0]["op"], "DC04")
        self.assertEqual([e["event"] for e in self.srv.bus.drain()], ["control_post", "control_ack"])


def synthetic_trial(name: str, arm: str, pair: str, cond: str, resp_bytes: int, t_shift: int = 0,
                    ax: int = 25) -> tuple[list[dict], list[dict]]:
    """A plausible fill->submit trial (events + Driver trace) on one monotonic timeline (ns)."""
    ms = 1_000_000
    b = 10_000 * ms + t_shift
    E: list[dict] = []
    T: list[dict] = []
    e = lambda t, n, **f: E.append({"event": n, "t_mono_ns": b + t * ms, **f})  # noqa: E731
    m = lambda t, p, **d: T.append({"t_mono_ns": b + t * ms, "seq": len(T), "phase": p, "session": "", "detail": d or None})  # noqa: E731
    e(0, "driver_spawn"); e(100, "call_send", label="navigate", tool="browser_navigate")
    e(200, "call_return", label="navigate", tool="browser_navigate", ok=True)
    seq = 0
    for step, base in ((1, 300), (2, 400)):
        e(base, "oracle_send", label=f"pre_step{step}"); e(base + 1, "oracle_return", label=f"pre_step{step}", outcome="unknown")
        e(base + 2, "call_send", label=f"snapshot{step}", tool="get_browser_state")
        m(base + 3, "mcp.line_read"); m(base + 4, "dispatch.enter"); m(base + 5, "snap.enter")
        for k, meth in enumerate(("Target.attachToTarget", "DOM.getDocument", "DOMSnapshot.captureSnapshot",
                                  "Page.getLayoutMetrics", "Accessibility.getFullAXTree")):
            seq += 1
            m(base + 6 + k, "cdp.send", id=seq, method=meth, on_session=k > 0, bytes=90)
            m(base + 6.5 + k, "cdp.reply", id=seq, bytes=1000 * (k + 1), error=False)
        m(base + 11, "snap.collected"); m(base + 11.2, "snap.acquired_dom", dom_nodes=40, layout_nodes=30)
        m(base + 11.3, "snap.acquired_ax", ax_nodes=ax)
        m(base + 12, "snap.oopif_done"); m(base + 13, "snap.paged"); m(base + 14, "snap.outcome")
        m(base + 15, "snap.stored"); m(base + 16, "snap.serialized"); m(base + 17, "dispatch.exit")
        m(base + 18, "mcp.handled"); m(base + 19, "mcp.serialized"); m(base + 20, "mcp.written")
        e(base + 21, "parse_start"); e(base + 22, "parse_end", bytes=resp_bytes)
        e(base + 23, "client_validate_start", tool="get_browser_state"); e(base + 24, "client_validate_end", tool="get_browser_state")
        e(base + 25, "call_return", label=f"snapshot{step}", tool="get_browser_state", ok=True)
        e(base + 26, "cand_start", step=step); e(base + 27, "cand_done", step=step, ids=[])
        e(base + 28, "decide_start", step=step); e(base + 28.1, "decided", step=step, choice="x")
        e(base + 29, "call_send", label=f"action{step}", tool="browser_type" if step == 1 else "browser_click")
        m(base + 30, "mcp.line_read"); m(base + 31, "click.enter" if step == 2 else "type.enter")
        if step == 1:
            m(base + 31.2, "focus.settle_start", settle_ms=100); m(base + 31.8, "focus.settle_end")
        m(base + 32, "click.cdp_send" if step == 2 else "type.insert_send")
        m(base + 33, "click.cdp_response" if step == 2 else "type.insert_response"); m(base + 34, "mcp.written")
        e(base + 35, "call_return", label=f"action{step}", tool="browser_type" if step == 2 else "browser_click", ok=True)
    e(436, "oracle_send", label="verify0"); e(437, "oracle_return", label="verify0", outcome="verified")
    e(440, "outcome_decided", outcome="verified"); e(450, "client_exited"); e(470, "browser_gone", ok=True, pids=3)
    controls = {"textbox:verification value": {"count": 1, "frame": "main", "visibility": "in_viewport", "actions": ["type"],
                                               "states": [], "value_is_token": False, "value_empty": True},
                "button:Submit": {"count": 1, "frame": "main", "visibility": "in_viewport", "actions": ["click"],
                                  "states": [], "value_is_token": False, "value_empty": True}}
    steps = [{"step": 1, "candidates": ["type-verification-value", "reobserve", "abstain"], "selected_nodes": 9 if arm == "A" else 4,
              "refs": 2, "outline_chars": 300 if arm == "A" else 120, "controls": controls},
             {"step": 2, "candidates": ["submit-form", "reobserve", "abstain"], "selected_nodes": 9 if arm == "A" else 4,
              "refs": 2, "outline_chars": 300 if arm == "A" else 120, "controls": controls}]
    summary = {"event": "summary", "trial": name, "plan": "ab", "arm": arm, "condition": cond, "pair": pair, "order": "AB",
               "cohort": "K1", "regime": "fresh-per-trial", "excluded": False, "outcome": "verified", "oracle_exact_match": True,
               "completion_mutations": 1, "wrong_target_submits": 0, "routes": ["provider", "provider"],
               "tools": ["browser_type", "browser_click"], "input_routes": [None, "dom_event"], "steps": steps,
               "journal": [{"event": "submit", "t_mono_ns": b + 435 * ms, "submitter": "original"}],
               "poller_first_ok_ns": b + 435 * ms + 1_500_000, "driver_env_trace_set": True, "query": None if arm == "A" else "q",
               "driver_trace": f"trials/{name}.driver-trace.jsonl", "loadavg_before": "1.0 1.0 1.0",
               "resources_at_outcome": {"clk_tck": 100, "driver_cpu_ticks": 12, "driver_status_kb": {"VmHWM": 9000},
                                        "browser_tree": {"pids": 3, "cpu_ticks": 50, "rss_kb": 300000}},
               "network": {"non_loopback_connect_attempts": 0}}
    E.append(summary)
    return E, T


class AnalyzeTests(unittest.TestCase):
    def test_build_from_synthetic_raw(self) -> None:
        import analyze
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "trials").mkdir()
            for i in range(3):
                for arm, rb in (("A", 5000), ("B_proj", 2000)):
                    name = f"ab{i:03d}-W-quiet-{arm}-none"
                    ev_, tr = synthetic_trial(name, arm, f"W-quiet-p{i:02d}", "W-quiet", rb)
                    (raw / "trials" / f"{name}.jsonl").write_text("\n".join(json.dumps(x) for x in ev_) + "\n")
                    (raw / "trials" / f"{name}.driver-trace.jsonl").write_text("\n".join(json.dumps(x) for x in tr) + "\n")
            summary, rows = analyze.build(raw)
        c = summary["cmp_ab"]["W-quiet"]
        self.assertEqual(c["pairs"], 3)
        self.assertTrue(c["acquisition"]["methods_equal_all_pairs"])
        self.assertTrue(c["acquisition"]["nodes_exact_all_pairs"])
        self.assertTrue(c["acquisition"]["equal"])
        self.assertEqual(c["semantic_equivalence"]["equivalent_pairs"], 3)
        self.assertEqual(c["savings_B_minus_A"]["response_bytes"]["median"], -6000)
        self.assertEqual(c["savings_B_minus_A"]["T_oracle_ms"]["median"], 0)
        d = summary["decomposition_A"]["W-quiet"]
        self.assertEqual(d["n"], 3)
        self.assertTrue(d["gate_named_coverage_gt_0_9"])
        self.assertAlmostEqual(sum(d["spans_mean_ms"].values()), d["T_oracle_mean_ms"], places=2)
        self.assertGreater(d["spans_mean_ms"]["observation acquisition"], 0)
        self.assertAlmostEqual(d["cleanup_mean_ms"], 30.0)
        self.assertEqual(len([r for r in rows if r["row_type"] == "trial"]), 6)
        self.assertEqual(summary["required_zero"]["duplicate_effect"], 0)
        self.assertEqual(summary["status"], "RAN")

    def test_acquisition_difference_is_reported(self) -> None:
        import analyze
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "trials").mkdir()
            for arm, ax in (("A", 25), ("B_proj", 24)):
                name = f"ab000-W-quiet-{arm}-none"
                ev_, tr = synthetic_trial(name, arm, "W-quiet-p00", "W-quiet", 100, ax=ax)
                (raw / "trials" / f"{name}.jsonl").write_text("\n".join(json.dumps(x) for x in ev_) + "\n")
                (raw / "trials" / f"{name}.driver-trace.jsonl").write_text("\n".join(json.dumps(x) for x in tr) + "\n")
            summary, _ = analyze.build(raw)
        acq = summary["cmp_ab"]["W-quiet"]["acquisition"]
        self.assertFalse(acq["nodes_exact_all_pairs"])
        self.assertFalse(acq["equal"])
        self.assertTrue(acq["diff_examples"])

    def test_blocked_build_without_trials(self) -> None:
        import analyze
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "run-manifest-preflight.json").write_text(json.dumps(
                {"plan_kind": "preflight", "status": "infrastructure_blocked", "lock_label": "x",
                 "preflight": {"ok": False, "checked": [{"candidate_index": 0, "reason": "uid_not_0"}]},
                 "network": {"non_loopback_connect_attempts": 0}}))
            summary, rows = analyze.build(raw)
        self.assertEqual(summary["status"], "BLOCKED")
        self.assertTrue(all(c["status"] == "BLOCKED" and c["trials"] == 0 for c in summary["cells"]))
        self.assertTrue(rows and all(r["row_type"] == "cell" for r in rows))


if __name__ == "__main__":
    unittest.main()
