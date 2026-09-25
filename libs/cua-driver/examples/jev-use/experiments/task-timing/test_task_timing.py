"""Controlled runner tests, not native desktop/provider qualification."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from task_timing import TaskTiming

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "baseline.py"
SCENARIOS = (
    "verified", "refuted", "empty_candidates", "provider_none", "abstain",
    "reobserve", "dry_run", "action_error", "observe_error", "provider_error",
    "verify_error", "reset_error", "cancel_action", "cleanup_error", "delayed_verify",
)


def load_runner(path: Path, name: str, scenario: str):
    evidence = {"calls": [], "events": [], "state": {"typed": False, "submitted": None},
                "oracle_reads": 0, "sleeps": [], "cleanup": []}
    state = evidence["state"]

    class Session:
        def __init__(self, *args): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): evidence["cleanup"].append("session")
        async def initialize(self): evidence["calls"].append(("initialize", {}))
        async def list_tools(self):
            evidence["calls"].append(("list_tools", {}))
            return types.SimpleNamespace(tools=[])
        async def call_tool(self, name, args):
            evidence["calls"].append((name, {k: v for k,v in args.items() if k != "session"}))
            if name == "browser_prepare": data = {"prepared_pid": 1}
            elif name == "list_windows":
                data = {"windows": [{"window_id": 1, "is_on_screen": True,
                                     "bounds": {"width": 100,"height": 100}}]}
            elif name == "get_browser_state":
                if args.get("snapshot_format") and scenario == "observe_error":
                    raise RuntimeError("test observation error")
                data = {"target_id": "owned-fixture", "tabs": [{"tab_id": "one"}],
                        "typed": state["typed"]}
            elif name == "browser_navigate": data = {}
            else:
                if scenario == "action_error": raise RuntimeError("test action error")
                if scenario == "cancel_action": raise asyncio.CancelledError()
                if name == "type_text": state["typed"] = True
                if name == "submit": state["submitted"] = "different" if scenario == "refuted" else "fixed"
                data = {}
            return types.SimpleNamespace(isError=False, structuredContent=data)

    @asynccontextmanager
    async def stdio(*args):
        try: yield None, None
        finally:
            evidence["cleanup"].append("transport")
            if scenario == "cleanup_error": raise RuntimeError("test cleanup error")

    mcp = types.ModuleType("mcp")
    mcp.ClientSession = Session
    mcp.StdioServerParameters = lambda **kwargs: kwargs
    client = types.ModuleType("mcp.client")
    stdio_module = types.ModuleType("mcp.client.stdio")
    stdio_module.stdio_client = stdio
    core = types.ModuleType("core")
    core.VisualObservation = object
    core.VisualObservationError = type("VisualObservationError", (Exception,), {})
    core.parse_visual_regions = lambda *args, **kwargs: None
    core.classify = lambda submitted, token, **kwargs: (
        "verified" if submitted == token else "refuted" if submitted is not None else "unknown")

    def build(snapshot, *args, **kwargs):
        if scenario == "empty_candidates": return []
        ident = (scenario if scenario in {"abstain","reobserve"} else
                 "submit-form" if state["typed"] else "type-verification-value")
        tool = "submit" if ident == "submit-form" else "type_text"
        return [types.SimpleNamespace(id=ident, tool=tool, arguments={"value": "fixed"})]
    core.build_candidates = build
    core.validate_choice = lambda choice, candidates, **kwargs: candidates[0]
    adapter = types.ModuleType("jev_adapter")
    def choose(candidates, *args, **kwargs):
        if scenario == "provider_error": raise RuntimeError("test provider error")
        return (None if scenario == "provider_none" else candidates[0].id, 1.0, {})
    adapter.choose_mock_adapter = choose
    adapter.choose_live = choose
    modules = {"mcp":mcp,"mcp.client":client,"mcp.client.stdio":stdio_module,
               "core":core,"jev_adapter":adapter}
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules): spec.loader.exec_module(module)

    def reset(url):
        if scenario == "reset_error": raise RuntimeError("test reset error")
    def oracle(url):
        evidence["oracle_reads"] += 1
        if scenario == "verify_error" and state["typed"]: raise RuntimeError("test verifier error")
        submitted = state["submitted"]
        if scenario == "delayed_verify" and evidence["oracle_reads"] < 5: submitted = None
        return {"submitted": submitted}
    async def sleep(delay): evidence["sleeps"].append(delay)
    module.reset_fixture = reset
    module.fixture_state = oracle
    module.write_event = lambda path, row: evidence["events"].append(row)
    module._test_sleep = sleep
    return module, evidence


def run_case(path, label, scenario, *, fail_timing_sink=False):
    module, evidence = load_runner(path, label, scenario)
    if fail_timing_sink:
        original = module.write_event
        def sink(path, row):
            if row["event"] in {"task_root","span"}: raise OSError("test full disk")
            original(path,row)
        module.write_event = sink
    args = argparse.Namespace(token="fixed", log=None, fixture_url="http://127.0.0.1:8765/",
                              max_steps=3, provider="mock", dry_run=scenario=="dry_run")
    with patch.object(module.asyncio, "sleep", module._test_sleep):
        try: outcome = asyncio.run(module.run(args)); error = None
        except BaseException as exc: outcome = None; error = type(exc).__name__
    evidence.update(outcome=outcome, error=error)
    return evidence


def semantic_events(events):
    return [{k:v for k,v in row.items() if not k.endswith("_ms")}
            for row in events if row["event"] not in {"task_root","span"}]


class RunnerTimingTests(unittest.TestCase):
    def test_controlled_baseline_parity(self):
        baseline_bytes = BASELINE.read_bytes()
        self.assertEqual(hashlib.sha1(b"blob "+str(len(baseline_bytes)).encode()+b"\0"+baseline_bytes).hexdigest(),
                         "003bdf23d41e7fa71a74583bb760d576503e908f")
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                before = run_case(BASELINE, "baseline", scenario)
                after = run_case(HERE/"run.py", "treatment", scenario)
                for key in ("calls","state","oracle_reads","sleeps","cleanup","outcome","error"):
                    self.assertEqual(before[key],after[key],key)
                self.assertEqual(semantic_events(before["events"]),semantic_events(after["events"]))
                self.assertEqual(sum(e.get("phase")=="verify" for e in after["events"]), after["oracle_reads"])
                roots = [e for e in after["events"] if e["event"]=="task_root"]
                self.assertEqual(len(roots),1)
                root=roots[0]
                self.assertEqual(root["outcome"], "cancelled" if scenario=="cancel_action" else
                                 after["outcome"] if after["error"] is None else "unknown")
                self.assertEqual(root["error_type"],after["error"])
                for span in (e for e in after["events"] if e["event"]=="span"):
                    self.assertEqual(span["task_id"],root["task_id"])
                    self.assertEqual(span["clock_id"],root["clock_id"])
                    self.assertLessEqual(0,span["start_ms"])
                    self.assertLessEqual(span["start_ms"],span["end_ms"])
                    self.assertLessEqual(span["end_ms"],root["end_ms"])
                if scenario=="delayed_verify":
                    self.assertTrue(any(e.get("phase")=="wait" for e in after["events"]))
                if scenario=="action_error":
                    self.assertTrue(any(e.get("phase")=="act" and e.get("error_type")=="RuntimeError"
                                        for e in after["events"]))

    def test_timing_sink_failure_preserves_return_and_exception(self):
        for scenario in ("verified","provider_error","cancel_action"):
            with self.subTest(scenario=scenario):
                before=run_case(BASELINE,"baseline",scenario)
                after=run_case(HERE/"run.py","treatment",scenario,fail_timing_sink=True)
                for key in ("outcome","error","calls","cleanup"):
                    self.assertEqual(before[key],after[key])

    def test_root_end_includes_cleanup_not_early_outcome(self):
        module, evidence = load_runner(HERE/"run.py", "treatment", "verified")
        ticks=iter(range(0,1000000000,1000000))
        module.TaskTiming=lambda: TaskTiming(clock=lambda:next(ticks))
        args=argparse.Namespace(token="fixed",log=None,fixture_url="http://127.0.0.1:8765/",
                                max_steps=3,provider="mock",dry_run=False)
        original=module.write_event
        def sink(path,row):
            if row["event"]=="task_root": self.assertEqual(evidence["cleanup"],["session","transport"])
            original(path,row)
        module.write_event=sink
        self.assertEqual(asyncio.run(module.run(args)),"verified")


class RecorderTests(unittest.TestCase):
    def test_exact_intervals_error_and_no_payload(self):
        ticks=iter([100,200,500,900])
        timer=TaskTiming(clock=lambda:next(ticks))
        with self.assertRaisesRegex(ValueError,"private test payload"):
            with timer.span("verify"): raise ValueError("private test payload")
        events=timer.finish("unknown",error_type="ValueError")
        self.assertEqual(events[0]["start_ms"],0.0001)
        self.assertEqual(events[0]["end_ms"],0.0004)
        self.assertEqual(events[-1]["end_ms"],0.0008)
        self.assertNotIn("private test payload",json.dumps(events))
        self.assertEqual(events[0]["error_type"],"ValueError")

    def test_capacity_is_explicit_not_silent(self):
        timer=TaskTiming(max_spans=1)
        with timer.span("one"): pass
        with timer.span("two"): pass
        events=timer.finish("unknown")
        self.assertEqual(len(events),2)
        self.assertEqual(events[-1]["dropped_spans"],1)

    def test_unique_task_clock_and_single_finish(self):
        one,two=TaskTiming(),TaskTiming()
        self.assertNotEqual(one.task_id,two.task_id)
        self.assertNotEqual(one.clock_id,two.clock_id)
        one.finish("abstained")
        with self.assertRaises(RuntimeError): one.finish("verified")
        two.finish("unknown")


if __name__=="__main__": unittest.main()
