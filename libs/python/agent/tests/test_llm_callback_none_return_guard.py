"""[muse] None-returning on_llm_start/on_llm_end callbacks must not poison the run loop.

Defect (fork main): ComputerAgent._on_llm_start/_on_llm_end assigned the
callback's return value unconditionally. A callback that forgets to return
(e.g. a logging-only on_llm_start) propagated None into the run loop:
- _on_llm_start -> None -> the Ollama image guard's `for m in None` raised
  TypeError, and predict_step received messages=None.
- _on_llm_end -> None -> `result["output"] = None` -> `new_items += None`
  raised TypeError.

Fix: a callback returning None is treated as "no change"; the previous
messages are kept. Documented in both docstrings.

Red-on-base: run this file against fork main (git checkout -- agent.py
after copying the fix aside) and the None cases return None / raise
TypeError on iteration.
"""
import asyncio
import importlib.util
import sys
import types as pytypes

REPO = "/home/hatch/workspace/scratch/cua-wt-muse-c58/libs/python/agent"


def _stub(name, **attrs):
    mod = pytypes.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load(pkg_name, file_path):
    spec = importlib.util.spec_from_file_location(pkg_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- dependency stubs -------------------------------------------------------
litellm = _stub("litellm")
litellm_utils = _stub("litellm.utils", function_to_dict=lambda f: {})
litellm.utils = litellm_utils
litellm_resp = _stub("litellm.responses")
litellm_resp_utils = _stub("litellm.responses.utils", Usage=type("Usage", (), {}))
litellm_resp.utils = litellm_resp_utils
litellm.responses = litellm_resp

cua_core = _stub("cua_core")
cua_core_telemetry = _stub(
    "cua_core.telemetry",
    is_telemetry_enabled=lambda: False,
    record_event=lambda *a, **k: None,
)
cua_core.telemetry = cua_core_telemetry

pkg = _stub("cua_agent")
pkg.__path__ = [REPO + "/cua_agent"]

_dict_param = type("DictParam", (dict,), {})

_openai = _stub("openai")
_openai_types = _stub("openai.types")
_openai_responses = _stub("openai.types.responses")
for _leaf, _names in {
    "openai.types.responses.easy_input_message_param": ["EasyInputMessageParam"],
    "openai.types.responses.response_computer_tool_call_param": [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionType", "ActionWait", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ],
    "openai.types.responses.response_function_tool_call_param": [
        "ResponseFunctionToolCallParam"
    ],
    "openai.types.responses.response_input_image_param": ["ResponseInputImageParam"],
    "openai.types.responses.response_output_message_param": [
        "ResponseOutputMessageParam"
    ],
    "openai.types.responses.response_output_text_param": ["ResponseOutputTextParam"],
    "openai.types.responses.response_reasoning_item_param": [
        "ResponseReasoningItemParam", "Summary"
    ],
}.items():
    _stub(_leaf, **{n: _dict_param for n in _names})

_stub(
    "cua_agent.adapters",
    AzureMLAdapter=object, CUAAdapter=object, HuggingFaceLocalAdapter=object,
    HumanAdapter=object, MLXVLMAdapter=object,
)
_stub(
    "cua_agent.callbacks",
    BudgetManagerCallback=object, ImageRetentionCallback=object,
    LoggingCallback=object, OperatorNormalizerCallback=object,
    OtelCallback=object, PromptInstructionsCallback=object,
    TelemetryCallback=object, TrajectorySaverCallback=object,
)
_stub(
    "cua_agent.computers",
    AsyncComputerHandler=object,
    is_agent_computer=lambda t: False,
    make_computer_handler=lambda s: None,
)
_stub("cua_agent.decorators", find_agent_config=lambda m: None)
_stub("cua_agent.tools")
_stub("cua_agent.tools.base", BaseComputerTool=object, BaseTool=object)
_stub(
    "cua_agent.types",
    AgentCapability=str,
    IllegalArgumentError=type("IllegalArgumentError", (ValueError,), {}),
    Messages=object,
    ToolError=type("ToolError", (Exception,), {}),
)

# ---- real modules under test -------------------------------------------------
_load("cua_agent.responses", REPO + "/cua_agent/responses.py")
agent_mod = _load("cua_agent.agent", REPO + "/cua_agent/agent.py")
ComputerAgent = agent_mod.ComputerAgent


def make_agent(callbacks):
    agent = object.__new__(ComputerAgent)
    agent.callbacks = callbacks
    return agent


class NoneStart:
    async def on_llm_start(self, messages):
        return None  # bug: forgot to return messages


class AppendStart:
    async def on_llm_start(self, messages):
        return messages + [{"role": "user", "content": "extra"}]


class NoneEnd:
    async def on_llm_end(self, messages):
        return None


class AppendEnd:
    async def on_llm_end(self, messages):
        return messages + [{"type": "message", "role": "assistant"}]


MSGS = [{"role": "user", "content": "hi"}]


def test_on_llm_start_none_return_keeps_messages():
    agent = make_agent([NoneStart()])
    out = asyncio.run(agent._on_llm_start(list(MSGS)))
    assert out == MSGS, f"None return poisoned messages: {out!r}"


def test_on_llm_start_transform_still_applies():
    agent = make_agent([AppendStart()])
    out = asyncio.run(agent._on_llm_start(list(MSGS)))
    assert out == MSGS + [{"role": "user", "content": "extra"}]


def test_on_llm_start_chain_skips_none():
    agent = make_agent([AppendStart(), NoneStart(), AppendStart()])
    out = asyncio.run(agent._on_llm_start(list(MSGS)))
    assert out == MSGS + [
        {"role": "user", "content": "extra"},
        {"role": "user", "content": "extra"},
    ]


def test_on_llm_start_none_result_iterable_like_ollama_guard():
    # Mirrors the Ollama image guard in run(): `for m in preprocessed`.
    agent = make_agent([NoneStart()])
    out = asyncio.run(agent._on_llm_start(list(MSGS)))
    seen = [m.get("role") for m in out]  # TypeError on base (None not iterable)
    assert seen == ["user"]


def test_on_llm_end_none_return_keeps_output():
    agent = make_agent([NoneEnd()])
    out = asyncio.run(agent._on_llm_end(list(MSGS)))
    assert out == MSGS, f"None return poisoned output: {out!r}"


def test_on_llm_end_transform_still_applies():
    agent = make_agent([AppendEnd()])
    out = asyncio.run(agent._on_llm_end(list(MSGS)))
    assert out == MSGS + [{"type": "message", "role": "assistant"}]


def test_on_llm_end_chain_skips_none():
    agent = make_agent([AppendEnd(), NoneEnd()])
    out = asyncio.run(agent._on_llm_end(list(MSGS)))
    assert out == MSGS + [{"type": "message", "role": "assistant"}]


def test_no_callbacks_passthrough():
    agent = make_agent([])
    assert asyncio.run(agent._on_llm_start(list(MSGS))) == MSGS
    assert asyncio.run(agent._on_llm_end(list(MSGS))) == MSGS


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} green")
    sys.exit(1 if failed else 0)
