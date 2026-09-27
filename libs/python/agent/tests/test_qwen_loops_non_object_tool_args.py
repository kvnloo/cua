"""Tests for non-object tool arguments in the Qwen-family loops.

The ``<tool_call>`` JSON in the priority-1 path is model-generated text, so
``arguments`` can be any valid JSON value, not just an object. On base,
``predict_step`` passed that value straight into ``_unnormalize_coordinate``,
whose unguarded ``args.get("coordinate")`` raised ``AttributeError`` and
killed the whole step. The priority-2 path had the same crash when a
provider ``tool_calls`` entry carried valid-but-non-object arguments (e.g.
the string ``"coordinate"`` passes the ``"coordinate" in args`` check, then
crashes in ``_unnormalize_coordinate``; other shapes crash in the responses
converter's ``action.get("action")``).

The fix degrades instead of crashing: non-object arguments are dropped and
the step falls through to the plain text-response path, so the model can
retry on the next step.

The real ``generic_vlm.py`` and ``qwen35.py`` are loaded with the litellm /
openai type imports stubbed (typing-only), so these tests exercise the
shipped code, not a mirror.
"""

import asyncio
import importlib.util
import json
import sys
import types

import pytest


def _stub_openai():
    stub_openai = types.ModuleType("openai")
    stub_types = types.ModuleType("openai.types")
    stub_responses = types.ModuleType("openai.types.responses")
    names = {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": [
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionWait",
            "ResponseComputerToolCallParam",
            "ActionType",
            "PendingSafetyCheck",
        ],
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }
    for mod_name, cls_names in names.items():
        mod = types.ModuleType(f"openai.types.responses.{mod_name}")
        for cls_name in cls_names:
            setattr(mod, cls_name, type(cls_name, (), {}))
        sys.modules[f"openai.types.responses.{mod_name}"] = mod
    sys.modules["openai"] = stub_openai
    sys.modules["openai.types"] = stub_types
    sys.modules["openai.types.responses"] = stub_responses


def _stub_litellm():
    litellm = types.ModuleType("litellm")
    litellm.acompletion = None
    resp = types.ModuleType("litellm.responses")
    trans = types.ModuleType("litellm.responses.litellm_completion_transformation")
    inner = types.ModuleType(
        "litellm.responses.litellm_completion_transformation.transformation"
    )

    class LiteLLMCompletionResponsesConfig:
        @staticmethod
        def _transform_chat_completion_usage_to_responses_usage(u):
            class U:
                def model_dump(self):
                    return {}

            return U()

    inner.LiteLLMCompletionResponsesConfig = LiteLLMCompletionResponsesConfig
    sys.modules["litellm"] = litellm
    sys.modules["litellm.responses"] = resp
    sys.modules["litellm.responses.litellm_completion_transformation"] = trans
    sys.modules[
        "litellm.responses.litellm_completion_transformation.transformation"
    ] = inner


def _load(agent_dir, mod_name, rel_path):
    path = f"{agent_dir}/{rel_path}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _load_modules():
    import pathlib

    agent_dir = str(pathlib.Path(__file__).resolve().parents[1])
    _stub_openai()
    _stub_litellm()

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [f"{agent_dir}/cua_agent"]
    sys.modules["cua_agent"] = pkg
    loops_pkg = types.ModuleType("cua_agent.loops")
    loops_pkg.__path__ = [f"{agent_dir}/cua_agent/loops"]
    sys.modules["cua_agent.loops"] = loops_pkg

    dec = types.ModuleType("cua_agent.decorators")

    def register_agent(**kwargs):
        def wrap(cls):
            return cls

        return wrap

    dec.register_agent = register_agent
    sys.modules["cua_agent.decorators"] = dec

    base = types.ModuleType("cua_agent.loops.base")

    class AsyncAgentConfig:
        pass

    base.AsyncAgentConfig = AsyncAgentConfig
    sys.modules["cua_agent.loops.base"] = base

    typ = types.ModuleType("cua_agent.types")
    typ.AgentCapability = str
    sys.modules["cua_agent.types"] = typ

    responses = _load(agent_dir, "cua_agent.responses", "cua_agent/responses.py")
    gvlm = _load(
        agent_dir, "cua_agent.loops.generic_vlm", "cua_agent/loops/generic_vlm.py"
    )
    qwen35 = _load(agent_dir, "cua_agent.loops.qwen35", "cua_agent/loops/qwen35.py")
    return gvlm, qwen35, responses


_gvlm, _qwen35, _responses = _load_modules()
_LOOPS = {"generic_vlm": _gvlm, "qwen35": _qwen35}
convert = _responses.convert_completion_messages_to_responses_items


def _require(mod, name):
    fn = getattr(mod, name, None)
    if fn is None:
        pytest.fail(f"{mod.__name__}.{name} missing (fix not applied)")
    return fn


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
@pytest.mark.parametrize(
    "args", ['"click"', '["click"]', "null", "42", '"coordinate"'], ids=["str", "list", "null", "num", "coord-str"]
)
def test_unnormalize_coordinate_non_object_passthrough(loop, args):
    """Non-object args have no coordinates: returned unchanged, no crash.

    Red on base: AttributeError from unguarded args.get("coordinate").
    """
    mod = _LOOPS[loop]
    out = asyncio.run(mod._unnormalize_coordinate(json.loads(args), (1920, 1080)))
    assert out == json.loads(args)


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_unnormalize_coordinate_dict_still_works(loop):
    """Positive control: dict args with coordinates are still unnormalized."""
    mod = _LOOPS[loop]
    out = asyncio.run(
        mod._unnormalize_coordinate({"coordinate": [500, 500]}, (2000, 1000))
    )
    assert out["coordinate"] == [1000, 500]


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
@pytest.mark.parametrize(
    "args_json, usable",
    [
        ('{"action": "left_click", "coordinate": [114, 68]}', True),
        ('"click"', False),
        ('["click"]', False),
        ("null", True),  # null/{} preserves base semantics: empty arguments object
        ("42", False),
        ("{}", True),
    ],
    ids=["object", "str", "list", "null", "num", "empty-object"],
)
def test_usable_tool_call_args(loop, args_json, usable):
    """_usable_tool_call_args gates the priority-1 path on dict arguments."""
    mod = _LOOPS[loop]
    fn = _require(mod, "_usable_tool_call_args")
    tool_call = {"name": "computer", "arguments": json.loads(args_json)}
    got = fn(tool_call)
    if usable:
        assert got == (json.loads(args_json) if json.loads(args_json) is not None else {})
    else:
        assert got is None


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_usable_tool_call_args_non_dict_call(loop):
    mod = _LOOPS[loop]
    fn = _require(mod, "_usable_tool_call_args")
    assert fn(None) is None
    assert fn("nope") is None


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
@pytest.mark.parametrize(
    "args_json",
    ['"click"', '["click"]', "null", "42", '"coordinate"'],
    ids=["str", "list", "null", "num", "coord-str"],
)
def test_normalize_provider_tool_call_drops_non_object_args(loop, args_json):
    """Priority-2 helper drops valid-but-non-object arguments instead of crashing."""
    mod = _LOOPS[loop]
    fn = _require(mod, "_normalize_provider_tool_call")
    tc = {
        "type": "function",
        "id": "call_0",
        "function": {"name": "computer", "arguments": args_json},
    }
    assert asyncio.run(fn(tc, (1920, 1080))) is None


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_normalize_provider_tool_call_keeps_malformed_json(loop):
    """Malformed JSON keeps the existing 'keep original' behavior."""
    mod = _LOOPS[loop]
    fn = _require(mod, "_normalize_provider_tool_call")
    tc = {
        "type": "function",
        "id": "call_0",
        "function": {"name": "computer", "arguments": "{not json"},
    }
    assert asyncio.run(fn(tc, (1920, 1080))) == tc


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_normalize_provider_tool_call_dict_args_still_work(loop):
    """Positive control: dict args are normalized and converted as before."""
    mod = _LOOPS[loop]
    fn = _require(mod, "_normalize_provider_tool_call")
    tc = {
        "type": "function",
        "id": "call_0",
        "function": {
            "name": "computer",
            "arguments": json.dumps({"action": "left_click", "coordinate": [500, 500]}),
        },
    }
    out = asyncio.run(fn(tc, (2000, 1000)))
    assert out is not None
    args = json.loads(out["function"]["arguments"])
    # unnormalized (500/1000 * 2000 = 1000, 500/1000 * 1000 = 500) then converted
    assert args["x"] == 1000 and args["y"] == 500


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_priority1_non_object_arguments_fall_back_to_text(loop):
    """End-to-end priority-1 degrade: unusable tool call -> text response, no crash.

    Replays predict_step's fixed priority-1 order with the real functions:
    parse the model text, gate on _usable_tool_call_args, and only build a
    tool-call item when the gate passes; otherwise emit the text response the
    else-branch produces.
    """
    mod = _LOOPS[loop]
    usable = _require(mod, "_usable_tool_call_args")
    text = 'Hmm <tool_call>{"name": "computer", "arguments": "click"}</tool_call>'
    tool_call = mod._parse_tool_call_from_text(text)
    assert isinstance(tool_call, dict)  # the parser finds the model-generated call
    args = usable(tool_call)
    assert args is None  # gate drops it
    items = convert([{"role": "assistant", "content": text}])
    assert len(items) == 1
    assert items[0]["type"] == "message"


@pytest.mark.parametrize("loop", ["generic_vlm", "qwen35"])
def test_priority1_object_arguments_still_build_tool_call(loop):
    """Positive control: well-formed tool calls still produce a computer_call."""
    mod = _LOOPS[loop]
    usable = _require(mod, "_usable_tool_call_args")
    text = (
        'Ok <tool_call>{"name": "computer", '
        '"arguments": {"action": "left_click", "coordinate": [500, 500]}}</tool_call>'
    )
    tool_call = mod._parse_tool_call_from_text(text)
    args = usable(tool_call)
    assert isinstance(args, dict)
    unnorm = asyncio.run(mod._unnormalize_coordinate(args, (2000, 1000)))
    fake_cm = {
        "role": "assistant",
        "tool_calls": [
            {
                "type": "function",
                "id": "call_0",
                "function": {
                    "name": tool_call.get("name") or "computer",
                    "arguments": json.dumps(unnorm),
                },
            }
        ],
    }
    items = convert([fake_cm])
    assert any(i["type"] == "computer_call" for i in items)
