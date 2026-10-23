"""Pure stdlib contract tests; fake objects below are unit fixtures, not live evals."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "examples" / "hobbylm_eval" / "harness.py"
SPEC = importlib.util.spec_from_file_location("hobbylm_eval_harness", PATH)
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def snapshot():
    return {"capabilities":{name:True for name in [*harness.APPS,"atspi","swaymsg","pactl","gsettings"]},
            "front_title":None,"apps":[],"calculator_text":[],"volume":50,"muted":False,
            "dark":False,"brightness":None,"timer":None,"calendar":"","answer":"",
            "screenshots":[],"question":""}


def task(kind, **target):
    return {"id":"unit-fixture","request":"unit fixture","oracle":{"kind":kind,**target}}


class SuiteTests(unittest.TestCase):
    def test_frozen_suite_has_post_variants_and_existing_benchmarks(self):
        suite, digest = harness.load_tasks()
        self.assertGreaterEqual(sum(t["id"].startswith("post-") for t in suite["tasks"]),13)
        existing = [t for t in suite["tasks"] if t["id"].startswith("cua-")]
        self.assertEqual(len(existing),5)
        self.assertTrue(all(t["source"].startswith("libs/cua-bench/tasks/") for t in existing))
        self.assertEqual(len(digest),64)
        self.assertEqual(suite["seed"],1729)
        self.assertEqual(suite["environment"],harness.ENVIRONMENT)
        by_id = {t["id"]:t for t in suite["tasks"]}
        self.assertEqual(by_id["post-demo-split-600"]["oracle"]["value"],"150")
        self.assertEqual(by_id["post-demo-eggs-seven-minutes"]["oracle"]["minutes"],7)
        self.assertEqual(by_id["post-demo-weather-tomorrow"]["oracle"]["kind"],"refusal")
        self.assertNotIn("@",by_id["post-synthetic-contact"]["request"])

    def test_duplicate_task_ids_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"tasks.json"
            path.write_text(json.dumps({"environment":harness.ENVIRONMENT,"tasks":[task("mute"),task("mute")]}))
            with self.assertRaises(ValueError): harness.load_tasks(path)

    def test_endpoint_must_not_embed_secrets(self):
        self.assertEqual(harness.validate_endpoint("http://127.0.0.1:13211"),"http://127.0.0.1:13211")
        for url in ("file:///tmp/socket","http://user:secret@localhost","http://localhost?token=x"):
            with self.subTest(url=url), self.assertRaises(ValueError): harness.validate_endpoint(url)


class ActionTests(unittest.TestCase):
    def test_ten_action_allowlist(self):
        self.assertEqual(harness.action_command("OPEN","Calculator"),{"mode":"open","app":"Calculator"})
        self.assertEqual(harness.action_command("TYPE","12*14="),{"mode":"type","text":"12*14="})
        self.assertEqual(harness.action_command("TIMER","15"),{"mode":"timer","minutes":15})
        self.assertEqual(harness.action_command("UNKNOWN",""),{"mode":"unknown"})
        self.assertEqual(harness.action_command("SCREENSHOT",""),{"mode":"screenshot"})

    def test_no_shell_or_arbitrary_text_escape(self):
        for name,argument in [("OPEN","Calculator; id"),("TYPE","hello"),("TYPE","1;id"),
                              ("TYPE","$(id)"),("FOLDER","../../etc"),("TIMER","121"),
                              ("TIMER","0"),("KEY","ctrl+q"),("EXEC","id"),("DONE","yes")]:
            with self.subTest(name=name,argument=argument), self.assertRaises(ValueError):
                harness.action_command(name,argument)

    def test_brightness_cannot_be_a_successful_noop(self):
        with self.assertRaises(NotImplementedError): harness.action_command("KEY","BRIGHTNESS_UP")
        self.assertFalse(harness.oracle(task("brightness",direction=1),snapshot(),snapshot(),"DONE"))

    def test_calendar_requires_exact_local_confirmation(self):
        argument = "Sandbox review | 2030-01-02 | 14:00 UTC | none"
        with self.assertRaises(ValueError): harness.action_command("EVENT",argument)
        confirmation = dict(harness.event_fields(argument),confirmed=True,local_only=True)
        command = harness.action_command("EVENT",argument,confirmation)
        self.assertEqual(command["event"]["person"],"none")
        with self.assertRaises(ValueError):
            harness.action_command("EVENT",argument.replace("14:00","15:00"),confirmation)


class OracleTests(unittest.TestCase):
    def test_model_claim_does_not_satisfy_final_state(self):
        before = snapshot()
        self.assertFalse(harness.oracle(task("calculator",value="55"),before,before,"DONE"))
        after = deepcopy(before)
        after["calculator_text"] = ["55"]
        self.assertTrue(harness.oracle(task("calculator",value="55"),before,after,"DONE"))
        after["calculator_text"] = ["155"]
        self.assertFalse(harness.oracle(task("calculator",value="55"),before,after,"DONE"))

    def test_volume_and_theme_require_actual_change(self):
        before, after = snapshot(), snapshot()
        self.assertFalse(harness.oracle(task("volume",direction=1),before,after,"DONE"))
        after["volume"] = 55
        self.assertTrue(harness.oracle(task("volume",direction=1),before,after,"DONE"))
        self.assertFalse(harness.oracle(task("volume",direction=-1),before,after,"DONE"))
        self.assertFalse(harness.oracle(task("dark",value=False),before,after,"DONE"))
        after["volume"] = 99
        self.assertFalse(harness.oracle(task("volume_exact",value=100),before,after,"DONE"))
        after["volume"] = 100
        self.assertTrue(harness.oracle(task("volume_exact",value=100),before,after,"DONE"))

    def test_refusal_requires_unchanged_state_and_unknown(self):
        before, after = snapshot(), snapshot()
        self.assertTrue(harness.oracle(task("refusal"),before,after,"UNKNOWN"))
        self.assertFalse(harness.oracle(task("refusal"),before,after,"DONE"))
        after["volume"] = 55
        self.assertFalse(harness.oracle(task("refusal"),before,after,"UNKNOWN"))

    def test_real_countdown_metadata_and_alive_process_required(self):
        before, after = snapshot(), snapshot()
        self.assertFalse(harness.oracle(task("timer",minutes=5),before,after,"DONE"))
        after["timer"] = {"duration_seconds":300,"remaining_seconds":295,"running":True}
        self.assertTrue(harness.oracle(task("timer",minutes=5),before,after,"DONE"))
        after["timer"]["running"] = False
        self.assertFalse(harness.oracle(task("timer",minutes=5),before,after,"DONE"))

    def test_calendar_is_local_and_exact(self):
        before, after = snapshot(), snapshot()
        target = task("event",title="Sandbox review",day="2030-01-02",time="14:00",person="none")
        after["calendar"] = "BEGIN:VCALENDAR\nSUMMARY:Sandbox review\nDTSTART:20300102T140000Z\nX-EVAL-CONTACT:none\nEND:VCALENDAR\n"
        self.assertTrue(harness.oracle(target,before,after,"DONE"))
        after["calendar"] += "ATTENDEE:mailto:person@example.com\n"
        self.assertFalse(harness.oracle(target,before,after,"DONE"))

    def test_contact_lookup_oracle_requires_real_contact_source(self):
        before, after = snapshot(), snapshot()
        target = task("event",title="Synthetic sync",day="2030-01-03",time="09:00",
                      person="eval-contact@example.invalid",contact_name="Eval Contact")
        after["calendar"] = "SUMMARY:Synthetic sync\nDTSTART:20300103T090000Z\nX-EVAL-CONTACT:eval-contact@example.invalid\n"
        self.assertFalse(harness.oracle(target,before,after,"DONE"))
        after["contacts"] = "BEGIN:VCARD\nFN:Eval Contact\nEMAIL:eval-contact@example.invalid\nEND:VCARD\n"
        self.assertTrue(harness.oracle(target,before,after,"DONE"))

    def test_missing_capabilities_unsupported_not_pass(self):
        before = snapshot()
        before["capabilities"]["atspi"] = False
        self.assertIn("atspi",harness.unsupported_reason(task("calculator",value="4"),before))
        self.assertIsNone(harness.unsupported_reason(task("timer",minutes=5),before))

    def test_two_existing_benchmarks_have_independent_answer_oracle(self):
        before, after = snapshot(), snapshot()
        self.assertFalse(harness.oracle(task("answer_file",value="Paris"),before,after,"DONE"))
        after["answer"] = " Paris\n"
        self.assertTrue(harness.oracle(task("answer_file",value="Paris"),before,after,"DONE"))

    def test_semantic_input_has_no_image_payload(self):
        text = harness.semantic_state(snapshot())
        self.assertIn("Calculator: not open",text)
        self.assertNotIn("base64",text)
        self.assertNotIn("image_url",text)


class MetricsTests(unittest.TestCase):
    def test_percentiles_and_empty_values(self):
        self.assertEqual(harness.percentile([4,1,3,2],.5),2.5)
        self.assertAlmostEqual(harness.percentile([4,1,3,2],.95),3.85)
        self.assertIsNone(harness.percentile([],.95))

    def test_unsupported_never_counts_as_pass_or_correct_refusal(self):
        rows = [{"status":"unsupported","oracle_kind":"calculator","steps":[],"wall_seconds":0},
                {"status":"passed","oracle_kind":"refusal","terminal":"UNKNOWN",
                 "steps":[{"generation_seconds":.52}],"wall_seconds":1}]
        result = harness.summarize(rows)
        self.assertEqual(result["passed"],1)
        self.assertEqual(result["unsupported"],1)
        self.assertEqual(result["correct_refusal_rate"],1)
        self.assertEqual(result["success_rate_all"],.5)
        self.assertAlmostEqual(result["published_reference_comparison"]["p50_ratio_to_mlx_replay_median"],.52/.262)
        self.assertAlmostEqual(result["published_reference_comparison"]["mean_ratio_to_mlx_live_mean"],.52/.806)

    def test_controlled_comparison_rejects_different_modality_or_initial_state(self):
        report = {"runtime":"hobbylm","seed":1729,"environment":harness.ENVIRONMENT,
                  "tasks_sha256":"abc","input_modality":"text-only","action_space":"ten-actions",
                  "max_steps":6,"max_new_tokens":64,"guest_fingerprint":{"os":"same"},
                  "initial_states":{"task":"same"},"generation_seconds_mean":.5,
                  "task_capabilities":{"task":{"atspi":True}},"supported_tasks":["task"]}
        other = deepcopy(report)
        other["runtime"] = "small-local"
        self.assertTrue(harness.compare_reports(report,other)["valid"])
        other["input_modality"] = "screenshots"
        self.assertFalse(harness.compare_reports(report,other)["valid"])
        other = deepcopy(report)
        other["initial_states"]["task"] = "different"
        self.assertFalse(harness.compare_reports(report,other)["valid"])
        other = deepcopy(report)
        other["task_capabilities"]["task"]["atspi"] = False
        self.assertFalse(harness.compare_reports(report,other)["valid"])
        other = deepcopy(report)
        other["supported_tasks"] = []
        self.assertFalse(harness.compare_reports(report,other)["valid"])


class OwnedTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_title_spoof_does_not_allow_typing_into_notes(self):
        keyboard = types.SimpleNamespace(type=mock.AsyncMock(), keypress=mock.AsyncMock())
        backend = harness.OwnedLinuxBackend(types.SimpleNamespace(keyboard=keyboard),"HobbyCuaEval")
        state = snapshot()
        state.update(front_title="Calculator", front_app="Notes", front_owned=True,
                     front_identity={"pid":7,"start_ticks":123})
        backend.snapshot = mock.AsyncMock(return_value=state)
        with self.assertRaisesRegex(ValueError,"verified owned Calculator"):
            await backend.action("TYPE 1=")
        keyboard.type.assert_not_awaited()
        keyboard.keypress.assert_not_awaited()

    async def test_focus_change_aborts_before_next_native_input(self):
        keyboard = types.SimpleNamespace(type=mock.AsyncMock(), keypress=mock.AsyncMock())
        backend = harness.OwnedLinuxBackend(types.SimpleNamespace(keyboard=keyboard),"HobbyCuaEval")
        owned = dict(snapshot(),front_app="Calculator",front_owned=True,
                     front_identity={"pid":7,"start_ticks":123})
        changed = dict(owned,front_identity={"pid":8,"start_ticks":456})
        backend.snapshot = mock.AsyncMock(side_effect=[owned,changed])
        with self.assertRaisesRegex(ValueError,"focus changed"):
            await backend.action("TYPE 1=")
        keyboard.type.assert_not_awaited()
        keyboard.keypress.assert_not_awaited()


class TraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_records_text_inputs_actions_and_each_screenshot(self):
        # This backend is explicitly a unit-test fixture, never an eval option.
        class Backend:
            async def reset(self, task): pass
            async def snapshot(self): return snapshot()
            async def observe(self): return harness.semantic_state(snapshot())
            async def screenshot(self): return b"\x89PNG\r\n\x1a\nunit-fixture"
            async def action(self, raw): return {"terminal":"unknown"}
        class Runtime:
            def complete(self, system, user, max_new=64):
                self.system, self.user = system, user
                return {"raw":"UNKNOWN","seconds":.2,"prompt_tokens":10,"output_tokens":1}
        helper = types.ModuleType("cua_agent.loops.hobbylm")
        helper.SYSTEM_V2 = "fixed ten actions"
        helper.format_user = lambda request,state,last_action=None,result=None: request + "\n" + state
        helper.parse_action = lambda raw: types.SimpleNamespace(name=raw,argument="")
        modules = {"cua_agent":types.ModuleType("cua_agent"),"cua_agent.loops":types.ModuleType("cua_agent.loops"),
                   "cua_agent.loops.hobbylm":helper}
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(sys.modules,modules):
            directory = Path(temporary)/"run"
            runtime = Runtime()
            row = await harness.run_task(Backend(),runtime,task("refusal"),directory,2,64)
            self.assertEqual(row["status"],"passed")
            self.assertEqual(row["terminal"],"UNKNOWN")
            self.assertEqual(len(row["steps"]),1)
            self.assertTrue((directory/"initial.png").exists())
            self.assertTrue((directory/"step-000.png").exists())
            self.assertTrue((directory/"final.png").exists())
            records = [json.loads(line) for line in (directory/"trace.jsonl").read_text().splitlines()]
            self.assertEqual([record["type"] for record in records],["initial","step","final"])
            self.assertEqual(records[1]["raw"],"UNKNOWN")
            self.assertIn("Calculator: not open",runtime.user)
            self.assertEqual(records[1]["system"],runtime.system)
            self.assertEqual(len(row["initial_state_sha256"]),64)
            unsupported = dict(task("brightness"),unsupported="No physical backlight")
            skipped = await harness.run_task(Backend(),runtime,unsupported,Path(temporary)/"unsupported",2,64)
            self.assertEqual(skipped["status"],"unsupported")
            self.assertEqual(skipped["steps"],[])
            class BrokenRuntime:
                def complete(self, *args, **kwargs): raise RuntimeError("unit loader failure")
            failed = await harness.run_task(Backend(),BrokenRuntime(),task("refusal"),Path(temporary)/"failure",2,64)
            self.assertEqual(failed["status"],"error")
            self.assertEqual(len(failed["steps"]),1)
            self.assertTrue((Path(temporary)/"failure"/"step-000.png").exists())


class SubprocessRuntimeTests(unittest.TestCase):
    def test_jsonl_reader_uses_actual_pipe_without_starting_a_model(self):
        reader, writer = os.pipe()
        worker = harness.SubprocessRuntime.__new__(harness.SubprocessRuntime)
        try:
            os.write(writer,b'{"ready":true}\n')
            with os.fdopen(reader,"rb",buffering=0) as stream:
                worker.process = types.SimpleNamespace(stdout=stream)
                self.assertEqual(worker._receive(),{"ready":True})
        finally:
            os.close(writer)

    def test_worker_completion_preserves_raw_output_and_seed(self):
        worker = harness.SubprocessRuntime.__new__(harness.SubprocessRuntime)
        worker.process = types.SimpleNamespace(stdin=io.BytesIO())
        worker.seed = 1730
        worker.memory = {}
        worker.hardware = {}
        reply = {"raw":"OPEN Calculator","seconds":.25,"prompt_tokens":12,"output_tokens":2,
                 "memory":{"cuda_peak_allocated_bytes":123,"cuda_peak_reserved_bytes":456}}
        worker._receive = lambda: reply
        self.assertEqual(worker.complete("system","semantic state",32),reply)
        sent = json.loads(worker.process.stdin.getvalue())
        self.assertEqual(sent,{"system":"system","user":"semantic state","max_new":32,"seed":1730})
        self.assertEqual(worker.memory["cuda_peak_allocated_bytes"],123)


if __name__ == "__main__":
    unittest.main()
