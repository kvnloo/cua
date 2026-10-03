"""Unit tests for the R2-07 compiled routine harness (UNIT evidence; no Driver, no browser).

run: <examples>/.venv/bin/python -m unittest discover -s <packet>/harness -p 'test_*.py' -v
(with <examples>/python on PYTHONPATH for the fallback test)
"""

from __future__ import annotations

import asyncio
import copy
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
EXAMPLES = os.environ.get("JEV_EXAMPLES")
if EXAMPLES:
    sys.path.insert(0, str(Path(EXAMPLES) / "python"))

import compiled_routine as cr  # noqa: E402

TOKEN = "tok-unit-1"
URL = "http://127.0.0.1:4321/"


def artifact() -> dict:
    return {
        "schema": cr.SCHEMA,
        "routine_id": "r2-07-fill-submit-v1",
        "task_class": "fill_submit",
        "steps": [
            {"logical_target": {"role": "textbox", "name": "verification value"}, "action": "browser_type",
             "param_slot": "token", "precondition": {"unique": True, "page_origin": cr.LOOPBACK_ORIGIN_PATTERN,
                                                     "field_state": "empty"}},
            {"logical_target": {"role": "button", "name": "Submit"}, "action": "browser_click",
             "input_route": "dom_event", "precondition": {"unique": True}, "depends_on": 0},
        ],
        "expected_outcome": {"oracle": "/state.submitted == token", "journal_submits": 1},
        "fallback_points": ["before each mutation: provider chooser"],
    }


def snap(n: int, *, value: str = "", submits: int = 1, field: bool = True, url: str = URL) -> dict:
    refs = []
    if field:
        refs.append({"ref": f"p{n}:0", "role": "textbox", "name": "verification value", "value": value,
                     "actions": ["type", "pointer"]})
    for i in range(submits):
        refs.append({"ref": f"p{n}:{i + 1}", "role": "button", "name": "Submit", "value": None,
                     "actions": ["click", "pointer"]})
    return {"snapshot": {"id": f"p{n}"}, "page": {"url": url}, "refs": refs, "target_id": "bt-x", "tab_id": "tab-x"}


class FakeDriver:
    """Scripted Driver: observations advance a snapshot counter; mutations follow a script."""

    def __init__(self, *, submits=1, field=True, prefill="", url=URL, click_script=None, type_ok=True):
        self.n = 0
        self.value = prefill
        self.submits, self.field, self.url = submits, field, url
        self.calls: list[tuple[str, dict]] = []
        self.click_script = list(click_script or ["ok"])
        self.landed = 0
        self.type_ok = type_ok

    async def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "get_browser_state":
            self.n += 1
            return snap(self.n, value=self.value, submits=self.submits, field=self.field, url=self.url)
        if name == "browser_type":
            assert args["ref"].startswith(f"p{self.n}:"), "dispatched a ref not from the latest observation"
            self.value = args["text"]
            return {"status": "ok", "effect": "applied"}
        if name == "browser_click":
            assert args["ref"].startswith(f"p{self.n}:"), "dispatched a ref not from the latest observation"
            step = self.click_script.pop(0) if self.click_script else "ok"
            if step == "stale":
                return {"status": "ok", "effect": "refused", "summary": "refused (browser_ref_stale): ref is stale"}
            if step == "transport_landed":
                self.landed += 1
                raise ConnectionResetError("connection closed")
            if step == "transport_lost":
                raise ConnectionResetError("connection closed")
            self.landed += 1
            return {"status": "ok", "effect": "unverifiable", "route": "dom"}
        raise AssertionError(name)


def ctx_for(driver: FakeDriver) -> cr.ReplayContext:
    return cr.ReplayContext(driver=driver, target_id="bt-x", tab_id="tab-x", pid=1, window_id=2, fixture_url=URL,
                            token=TOKEN, read_oracle=lambda: {"submitted": TOKEN if driver.landed else None})


def replay(art, driver, **kw):
    routine = cr.Routine(art, **kw)
    routine.RECONCILE_DEADLINE_S = 0.2
    routine.VERIFY_DEADLINE_S = 0.2
    rec = cr.ReplayRecord()
    asyncio.run(routine.replay(ctx_for(driver), rec))
    return rec


class AuthorityTests(unittest.TestCase):
    def test_clean_artifact_passes(self):
        self.assertEqual(cr.check_artifact_authority(artifact()), [])

    def test_rejects_every_authority_field(self):
        cases = {
            "ref": ("steps", 1, "ref", "p3:1"),
            "element_token": ("steps", 0, "element_token", "et-abcdef123"),
            "capture_id": ("steps", 0, "capture_id", "c1"),
            "target_id": ("steps", 0, "target_id", "bt-1234567890"),
            "tab_id": ("steps", 0, "tab_id", "tab-1234567890"),
            "session": ("steps", 0, "session", "jev-python-abcd1234"),
            "session_epoch": ("steps", 0, "session_epoch", 3),
            "generation": ("steps", 0, "generation", 2),
            "backend_node_id": ("steps", 1, "backend_node_id", 17),
            "x": ("steps", 1, "x", 100),
            "y": ("steps", 1, "y", 200),
            "coordinates": ("steps", 1, "coordinates", [1, 2]),
            "bounds": ("steps", 1, "bounds", {"w": 1}),
            "pid": ("steps", 0, "pid", 42),
            "window_id": ("steps", 0, "window_id", 42),
            "snapshot_id": ("steps", 0, "snapshot_id", "p3"),
        }
        for label, (k1, idx, key, value) in cases.items():
            with self.subTest(label):
                art = artifact()
                art[k1][idx][key] = value
                problems = cr.check_artifact_authority(art)
                self.assertTrue(any(key in p for p in problems), problems)
                with self.assertRaises(cr.ArtifactAuthorityError):
                    cr.Routine(art)

    def test_rejects_authority_smuggled_as_values(self):
        for value in ("p12:3", "bt-0123456789ab", "tab-0123456789ab", "jev-python-0a1b2c3d",
                      "123e4567-e89b-12d3-a456-426614174000"):
            with self.subTest(value):
                art = artifact()
                art["steps"][1]["logical_target"]["name"] = value
                self.assertTrue(cr.check_artifact_authority(art))

    def test_rejects_float_coordinates_and_extra_target_keys(self):
        art = artifact()
        art["steps"][1]["logical_target"]["ref"] = "p1:1"
        self.assertTrue(cr.check_artifact_authority(art))
        art = artifact()
        art["steps"][1]["precondition"]["unique"] = 0.5
        self.assertTrue(cr.check_artifact_authority(art))

    def test_requires_unique_and_earlier_dependency(self):
        art = artifact()
        art["steps"][1]["precondition"]["unique"] = False
        self.assertTrue(cr.check_artifact_authority(art))
        art = artifact()
        art["steps"][1]["depends_on"] = 1
        self.assertTrue(cr.check_artifact_authority(art))


class CompileTests(unittest.TestCase):
    def trace(self, *, duplicate=False, literal=False):
        sem1 = {"kind": "driver_call", "ok": True, "tool": "get_browser_state", "arg_snapshot_format": "semantic_v2",
                "page_url": "http://127.0.0.1:5555/", "refs_logical": [
                    {"ref": "p1:0", "role": "textbox", "name": "verification value", "value_state": "empty"},
                    {"ref": "p1:1", "role": "button", "name": "Submit", "value_state": "empty"}]}
        sem2 = copy.deepcopy(sem1)
        for e in sem2["refs_logical"]:
            e["ref"] = e["ref"].replace("p1", "p2")
        if duplicate:
            sem2["refs_logical"].append({"ref": "p2:2", "role": "button", "name": "Submit", "value_state": "empty"})
        return [
            {"kind": "provider_response", "ok": True, "backend": "typesafe"},
            sem1,
            {"kind": "driver_call", "ok": True, "tool": "browser_type", "arg_ref": "p1:0", "arg_text_is_token": not literal},
            {"kind": "provider_response", "ok": True, "backend": "typesafe"},
            sem2,
            {"kind": "driver_call", "ok": True, "tool": "browser_click", "arg_ref": "p2:1", "arg_input_route": "dom_event"},
        ]

    def test_compiles_logical_artifact_without_authority(self):
        art = cr.compile_trace(self.trace(), learning_verified=True, routine_id="r2-07-fill-submit-v1")
        self.assertEqual(cr.check_artifact_authority(art), [])
        self.assertEqual(art["steps"][0]["logical_target"], {"role": "textbox", "name": "verification value"})
        self.assertEqual(art["steps"][0]["precondition"]["field_state"], "empty")
        self.assertEqual(art["steps"][1]["input_route"], "dom_event")
        self.assertEqual(art["steps"][1]["depends_on"], 0)
        self.assertNotIn("p1:0", cr.dumps(art))
        self.assertEqual(art["compiled_from"]["learning_provider_decisions"], 2)

    def test_refuses_unverified_trace_duplicates_and_literals(self):
        with self.assertRaises(cr.CompileError):
            cr.compile_trace(self.trace(), learning_verified=False, routine_id="r")
        with self.assertRaises(cr.CompileError):
            cr.compile_trace(self.trace(duplicate=True), learning_verified=True, routine_id="r")
        with self.assertRaises(cr.CompileError):
            cr.compile_trace(self.trace(literal=True), learning_verified=True, routine_id="r")


class ReplayTests(unittest.TestCase):
    def test_happy_path_binds_fresh_before_every_mutation(self):
        d = FakeDriver()
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "verified")
        names = [c[0] for c in d.calls]
        self.assertEqual(names, ["get_browser_state", "browser_type", "get_browser_state", "browser_click"])
        self.assertTrue(all(m["fresh"] for m in rec.mutations))
        self.assertEqual(rec.provider_decisions, 0)

    def test_ambiguous_submit_never_dispatches(self):
        d = FakeDriver(submits=2)
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "stopped")
        self.assertNotIn("browser_click", [c[0] for c in d.calls])
        self.assertIn("target_ambiguous", rec.stop_reason)

    def test_missing_submit_and_out_of_domain_page(self):
        rec = replay(artifact(), FakeDriver(submits=0))
        self.assertEqual(rec.outcome, "stopped")
        d = FakeDriver(field=False, submits=0)
        rec = replay(artifact(), d)
        self.assertEqual([c[0] for c in d.calls], ["get_browser_state"])
        self.assertIn("target_not_found", rec.stop_reason)

    def test_prefilled_value_fails_precondition(self):
        d = FakeDriver(prefill="something-else")
        rec = replay(artifact(), d)
        self.assertIn("field_state", rec.stop_reason)
        self.assertEqual([c[0] for c in d.calls], ["get_browser_state"])

    def test_wrong_origin_fails_precondition(self):
        d = FakeDriver(url="http://example.com/")
        rec = replay(artifact(), d)
        self.assertIn("page_origin", rec.stop_reason)

    def test_stale_refusal_gets_exactly_one_rebind(self):
        d = FakeDriver(click_script=["stale", "ok"])
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "verified")
        self.assertEqual([m["result"] for m in rec.mutations], ["accepted", "refused", "accepted"])
        d = FakeDriver(click_script=["stale", "stale"])
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "stopped")
        self.assertEqual(sum(1 for c in d.calls if c[0] == "browser_click"), 2)

    def test_ack_loss_reconciles_and_never_redispatches(self):
        d = FakeDriver(click_script=["transport_landed"])
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "verified_by_reconcile")
        self.assertEqual(sum(1 for c in d.calls if c[0] == "browser_click"), 1)
        d = FakeDriver(click_script=["transport_lost"])
        rec = replay(artifact(), d)
        self.assertEqual(rec.outcome, "unknown")
        self.assertEqual(sum(1 for c in d.calls if c[0] == "browser_click"), 1)
        self.assertEqual(sum(1 for c in d.calls if c[0] == "browser_type"), 1, "never restarts from step 1")

    def test_dependency_postcondition_checked_before_submit(self):
        class LosesValue(FakeDriver):
            async def call(self, name, args):
                out = await super().call(name, args)
                if name == "browser_type":
                    self.value = ""
                return out
        d = LosesValue()
        rec = replay(artifact(), d)
        self.assertIn("dependency_postcondition", rec.stop_reason)
        self.assertNotIn("browser_click", [c[0] for c in d.calls])


@unittest.skipUnless(EXAMPLES, "set JEV_EXAMPLES to the jev-use examples dir")
class FallbackTests(unittest.TestCase):
    def test_fallback_filters_ambiguous_candidates(self):
        from tasks import FixtureFormTask

        d = FakeDriver(submits=2)
        fb = cr.make_chooser_fallback(runner=None, task_factory=lambda t, u: FixtureFormTask(t, u), provider="mock")
        rec = replay(artifact(), d, fallback=fb)
        self.assertEqual(rec.outcome, "stopped")
        self.assertNotIn("browser_click", [c[0] for c in d.calls])
        self.assertTrue(any(e["kind"] == "fallback_candidate_dropped_not_unique" for e in rec.events))

    def test_fallback_continues_from_current_state(self):
        from tasks import FixtureFormTask

        d = FakeDriver(prefill="other")
        fb = cr.make_chooser_fallback(runner=None, task_factory=lambda t, u: FixtureFormTask(t, u), provider="mock")
        rec = replay(artifact(), d, fallback=fb)
        self.assertEqual(rec.outcome, "fallback_verified")
        self.assertTrue(all(m["fresh"] for m in rec.mutations))


if __name__ == "__main__":
    unittest.main()
