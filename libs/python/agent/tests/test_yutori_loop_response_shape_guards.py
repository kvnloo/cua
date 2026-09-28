"""Shape guards in the Yutori n1 loop's provider-response parsing.

YutoriN1Config.predict_step parsed the litellm response with
``(resp_dict.get("choices") or [{}])[0]`` and unguarded ``.get`` calls on
the choice/message/tool_call/function payloads. Malformed provider
shapes raised KeyError/AttributeError out of predict_step (non-retryable
-> run-kill): choices as a dict, non-dict choice or message entries,
non-list tool_calls, non-dict tool calls, non-dict function payloads, and
non-dict parsed arguments. _convert_n1_action_to_computer_action also
crashed on non-dict args (.get) and non-str key_comb (.split). No
existing muse/* branch touches loops/yutori.py, so these shapes were
uncovered.

Malformed payloads now degrade to empty shapes (empty choices/message,
skipped tool calls, None action conversion); well-formed parsing and
conversion are unchanged.

Self-contained: litellm, the litellm responses transformation, PIL-adjacent
paths, and the cua_agent package relatives are stubbed; predict_step runs
with a fake response object and no computer handler. Runs under pytest or
plain ``python3 <file>``.
"""

import asyncio
import json
import os
import sys
import types
import unittest

# ---- Stub litellm ---------------------------------------------------------
litellm = types.ModuleType("litellm")
litellm.acompletion = None  # replaced per-test
_litellm_responses = types.ModuleType("litellm.responses")
_litellm_lct = types.ModuleType("litellm.responses.litellm_completion_transformation")
_litellm_trans = types.ModuleType(
    "litellm.responses.litellm_completion_transformation.transformation"
)


class _Usage:
    def model_dump(self):
        return {}


class _Cfg:
    @staticmethod
    def _transform_chat_completion_usage_to_responses_usage(usage):
        return _Usage()


_litellm_trans.LiteLLMCompletionResponsesConfig = _Cfg
for _name, _mod in {
    "litellm": litellm,
    "litellm.responses": _litellm_responses,
    "litellm.responses.litellm_completion_transformation": _litellm_lct,
    "litellm.responses.litellm_completion_transformation.transformation": _litellm_trans,
}.items():
    sys.modules[_name] = _mod

# ---- Stub cua_agent package relatives --------------------------------------
_pkg = types.ModuleType("cua_agent")
_pkg.__path__ = []
_decorators = types.ModuleType("cua_agent.decorators")
_decorators.register_agent = lambda **kw: (lambda cls: cls)
_loops_pkg = types.ModuleType("cua_agent.loops")
_loops_pkg.__path__ = []
_loops_base = types.ModuleType("cua_agent.loops.base")


class AsyncAgentConfig:
    pass


_loops_base.AsyncAgentConfig = AsyncAgentConfig
_responses = types.ModuleType("cua_agent.responses")
_responses.convert_responses_items_to_completion_messages = (
    lambda messages, **kw: [m for m in messages if isinstance(m, dict)]
)
_responses.convert_completion_messages_to_responses_items = (
    lambda messages: [{"converted": m} for m in messages]
)
_responses.make_function_call_item = (
    lambda name, args, call_id=None: {
        "type": "function_call",
        "name": name,
        "arguments": args,
        "call_id": call_id,
    }
)
_responses.make_output_text_item = lambda text: {"type": "message", "text": text}
_responses.make_reasoning_item = lambda text: {"type": "reasoning", "text": text}
_types = types.ModuleType("cua_agent.types")
_types.AgentCapability = str
for _name, _mod in {
    "cua_agent": _pkg,
    "cua_agent.decorators": _decorators,
    "cua_agent.loops": _loops_pkg,
    "cua_agent.loops.base": _loops_base,
    "cua_agent.responses": _responses,
    "cua_agent.types": _types,
}.items():
    sys.modules[_name] = _mod

import importlib.util  # noqa: E402

_LOOP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "cua_agent", "loops", "yutori.py"
)
_spec = importlib.util.spec_from_file_location("cua_agent.loops.yutori", _LOOP_PATH)
yutori = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(yutori)

IMG_MSG = {
    "role": "user",
    "content": [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,notreallyb64"}}
    ],
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.usage = object()
        self._hidden_params = {}

    def model_dump(self):
        return self._payload


def _run_predict(payload):
    async def _fake_acompletion(**kw):
        return _FakeResponse(payload)

    litellm.acompletion = _fake_acompletion
    agent = yutori.YutoriN1Config()
    return asyncio.run(agent.predict_step([dict(IMG_MSG)], model="yutori/n1"))


def _output_texts(result):
    return [
        i.get("text")
        for i in result["output"]
        if isinstance(i, dict) and i.get("type") == "message"
    ]


class ResponseParseShapeGuards(unittest.TestCase):
    def test_choices_none(self):
        result = _run_predict({})
        self.assertIn("Task completed.", _output_texts(result))

    def test_choices_as_dict(self):
        result = _run_predict({"choices": {"0": {}}})
        self.assertIn("Task completed.", _output_texts(result))

    def test_choice_non_dict(self):
        result = _run_predict({"choices": ["oops"]})
        self.assertIn("Task completed.", _output_texts(result))

    def test_message_non_dict(self):
        result = _run_predict({"choices": [{"message": "oops"}]})
        self.assertIn("Task completed.", _output_texts(result))

    def test_tool_calls_non_list(self):
        result = _run_predict(
            {"choices": [{"message": {"content": "", "tool_calls": {"0": {}}}}]}
        )
        self.assertIn("Task completed.", _output_texts(result))

    def test_tool_call_non_dict_skipped(self):
        # Malformed tool calls are skipped; the truthy tool_calls_array means
        # the no-tool-call "Task completed." branch does not run either.
        result = _run_predict(
            {"choices": [{"message": {"content": "", "tool_calls": ["oops", 42]}}]}
        )
        self.assertEqual(result["output"], [])

    def test_function_non_dict(self):
        result = _run_predict(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {"id": "c1", "function": "oops"},
                            ],
                        }
                    }
                ]
            }
        )
        fn_items = [
            i
            for i in result["output"]
            if isinstance(i, dict) and i.get("type") == "function_call"
        ]
        self.assertEqual(len(fn_items), 1)
        self.assertEqual(fn_items[0]["arguments"], {})

    def test_arguments_non_dict(self):
        result = _run_predict(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {
                                        "name": "goto_url",
                                        "arguments": '["not","a","dict"]',
                                    },
                                },
                            ],
                        }
                    }
                ]
            }
        )
        # goto_url converts to a "computer" action; args {} -> url "".
        converted = [
            i for i in result["output"] if isinstance(i, dict) and "converted" in i
        ]
        self.assertEqual(len(converted), 1)
        args = json.loads(
            converted[0]["converted"]["tool_calls"][0]["function"]["arguments"]
        )
        self.assertEqual(args["action"], "visit_url")
        self.assertEqual(args["url"], "")

    def test_well_formed_tool_call_preserved(self):
        result = _run_predict(
            {
                "choices": [
                    {
                        "message": {
                            "content": "clicking",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "function": {
                                        "name": "left_click",
                                        "arguments": '{"coordinates": [500, 500]}',
                                    },
                                },
                            ],
                        }
                    }
                ]
            }
        )
        converted = [
            i for i in result["output"] if isinstance(i, dict) and "converted" in i
        ]
        self.assertEqual(len(converted), 1)
        self.assertEqual(
            converted[0]["converted"]["tool_calls"][0]["function"]["name"], "computer"
        )


class ActionConverterShapeGuards(unittest.TestCase):
    def test_args_non_dict(self):
        self.assertIsNone(
            yutori._convert_n1_action_to_computer_action("left_click", "oops", 1920, 1080)
        )

    def test_key_comb_non_str(self):
        self.assertIsNone(
            yutori._convert_n1_action_to_computer_action(
                "key_press", {"key_comb": 42}, 1920, 1080
            )
        )

    def test_well_formed_left_click(self):
        out = yutori._convert_n1_action_to_computer_action(
            "left_click", {"coordinates": [500, 500]}, 1920, 1080
        )
        self.assertEqual(out["action"], "left_click")
        self.assertEqual(out["x"], 960)
        self.assertEqual(out["y"], 540)

    def test_well_formed_key_press(self):
        out = yutori._convert_n1_action_to_computer_action(
            "key_press", {"key_comb": "Control+a"}, 1920, 1080
        )
        self.assertEqual(out["keys"], ["Control", "a"])


if __name__ == "__main__":
    unittest.main()
