"""Red-on-base tests: run() must degrade (not crash) on malformed step results.

Defects (all on fork main, ComputerAgent.run in cua_agent/agent.py):
1. A loop returning a result whose "output" is a non-list (e.g. a string)
   crashed the run: `new_items += <str>` splinters into chars and
   `_handle_item` then dies on `'o'.get` (AttributeError).
2. A loop returning a non-dict result (None / list) crashed on
   `result["output"] = ...` (TypeError).
3. A non-dict entry inside `_handle_item`'s partial_items crashed the
   partial-item scan on `pi.get` (AttributeError).

The harness loads the REAL cua_agent.agent + cua_agent.responses with stubbed
litellm / openai / cua_core / sibling submodules (none installed here).
"""

import asyncio
import importlib.util
import sys
import types as pytypes
from pathlib import Path

AGENT_PKG = Path(__file__).resolve().parents[1] / "cua_agent"


def _stub(name):
    mod = pytypes.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _pkg(name):
    mod = _stub(name)
    mod.__path__ = []
    return mod


def _ensure_harness():
    if "cua_agent.agent" in sys.modules:
        return
    base = _pkg("cua_agent")
    base.__path__ = [str(AGENT_PKG)]

    # --- stub openai.types.responses.* (imported by real responses.py) ---
    openai = _stub("openai")
    otypes = _pkg("openai.types")
    oresp = _pkg("openai.types.responses")
    openai.types = otypes
    otypes.responses = oresp

    def _osub(name, names):
        m = _stub(f"openai.types.responses.{name}")
        for n in names:
            setattr(m, n, type(n, (), {}))
        setattr(oresp, name, m)

    _osub("easy_input_message_param", ["EasyInputMessageParam"])
    _osub(
        "response_computer_tool_call_param",
        [
            "ActionClick",
            "ActionDoubleClick",
            "ActionDrag",
            "ActionDragPath",
            "ActionKeypress",
            "ActionMove",
            "ActionScreenshot",
            "ActionScroll",
            "ActionType",
            "ActionWait",
            "PendingSafetyCheck",
            "ResponseComputerToolCallParam",
        ],
    )
    _osub("response_function_tool_call_param", ["ResponseFunctionToolCallParam"])
    _osub("response_input_image_param", ["ResponseInputImageParam"])
    _osub("response_output_message_param", ["ResponseOutputMessageParam"])
    _osub("response_output_text_param", ["ResponseOutputTextParam"])
    _osub("response_reasoning_item_param", ["ResponseReasoningItemParam", "Summary"])

    # --- stub litellm (+ litellm.utils, litellm.responses.utils.Usage) ---
    litellm = _stub("litellm")
    litellm_utils = _stub("litellm.utils")
    litellm_responses = _pkg("litellm.responses")
    litellm_responses_utils = _stub("litellm.responses.utils")

    class Usage:
        def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0):
            self.prompt_tokens = prompt_tokens
            self.completion_tokens = completion_tokens
            self.total_tokens = total_tokens

    litellm_responses_utils.Usage = Usage
    litellm.responses = litellm_responses
    litellm.utils = litellm_utils
    litellm_responses.utils = litellm_responses_utils

    # --- stub cua_core.telemetry ---
    cua_core = _pkg("cua_core")
    telemetry = _stub("cua_core.telemetry")
    telemetry.is_telemetry_enabled = lambda: False
    telemetry.record_event = lambda *a, **k: None
    cua_core.telemetry = telemetry

    # --- stub sibling cua_agent submodules (names agent.py imports) ---
    adapters = _pkg("cua_agent.adapters")
    for n in (
        "AzureMLAdapter",
        "CUAAdapter",
        "HuggingFaceLocalAdapter",
        "HumanAdapter",
        "MLXVLMAdapter",
    ):
        setattr(adapters, n, type(n, (), {}))
    callbacks = _pkg("cua_agent.callbacks")
    for n in (
        "BudgetManagerCallback",
        "ImageRetentionCallback",
        "LoggingCallback",
        "OperatorNormalizerCallback",
        "OtelCallback",
        "PromptInstructionsCallback",
        "TelemetryCallback",
        "TrajectorySaverCallback",
    ):
        setattr(callbacks, n, type(n, (), {}))
    computers = _pkg("cua_agent.computers")
    computers.AsyncComputerHandler = type("AsyncComputerHandler", (), {})
    computers.is_agent_computer = lambda t: False
    computers.make_computer_handler = lambda *a, **k: None
    decorators = _pkg("cua_agent.decorators")

    def register_agent(*dargs, **dkwargs):
        def deco(cls):
            return cls

        return deco

    decorators.register_agent = register_agent
    decorators.find_agent_config = lambda model: None
    tools = _pkg("cua_agent.tools")
    tools_base = _stub("cua_agent.tools.base")
    tools_base.BaseComputerTool = type("BaseComputerTool", (), {})
    tools_base.BaseTool = type("BaseTool", (), {})
    tools.base = tools_base
    types_mod = _stub("cua_agent.types")
    types_mod.AgentCapability = str
    types_mod.IllegalArgumentError = type("IllegalArgumentError", (Exception,), {})
    types_mod.Messages = list
    types_mod.ToolError = type("ToolError", (Exception,), {})
    types_mod.AgentResponse = dict
    types_mod.Tools = list
    types_mod.AgentConfigInfo = type("AgentConfigInfo", (), {})
    loops = _pkg("cua_agent.loops")
    loops_base = _stub("cua_agent.loops.base")
    loops_base.AsyncAgentConfig = type("AsyncAgentConfig", (), {})
    loops.base = loops_base

    def _load_real(modname, path):
        spec = importlib.util.spec_from_file_location(modname, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[modname] = mod
        spec.loader.exec_module(mod)
        return mod

    _load_real("cua_agent.responses", AGENT_PKG / "responses.py")
    _load_real("cua_agent.agent", AGENT_PKG / "agent.py")


_ensure_harness()
agent_mod = sys.modules["cua_agent.agent"]


def make_agent(loop_result, handle_item_result=()):
    """ComputerAgent with a fake loop; real run() drives the defects."""
    ag = object.__new__(agent_mod.ComputerAgent)
    ag.model = "test-model"
    ag.kwargs = {}
    ag.api_key = None
    ag.api_base = None
    ag.tool_schemas = []
    ag.computer_handler = None
    ag.callbacks = []
    ag.max_retries = 0
    ag.use_prompt_caching = False
    ag.telemetry_enabled = False
    ag.tools = []

    class FakeConfig:
        tool_type = None
        agent_class = type("FakeLoopClass", (), {})

    ag.agent_config_info = FakeConfig()

    class FakeLoop:
        async def predict_step(self, **kw):
            return loop_result

        def get_capabilities(self):
            return ["step"]

    ag.agent_loop = FakeLoop()

    async def noop_computers():
        return None

    ag._initialize_computers = noop_computers

    calls = {"n": 0}

    async def fake_handle_item(item, computer=None, ignore_call_ids=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return list(handle_item_result)
        return []

    ag._handle_item = fake_handle_item
    return ag


def run_all(ag):
    async def collect():
        return [r async for r in ag.run([{"role": "user", "content": "hi"}])]

    return asyncio.run(collect())


ASSISTANT_MSG = {
    "type": "message",
    "role": "assistant",
    "content": [{"type": "output_text", "text": "done"}],
}


def test_non_list_output_degrades_to_empty_turn():
    # Loop returns a string "output": base splinters it into chars and dies
    # in _handle_item; fixed code coerces to [] and the run completes.
    ag = make_agent({"output": "oops", "usage": {}})
    results = run_all(ag)
    assert len(results) == 1
    assert results[0]["output"] == []


def test_non_dict_result_degrades_to_empty_turn():
    # Loop returns None: base dies on result["output"] = ... (TypeError).
    ag = make_agent(None)
    results = run_all(ag)
    assert len(results) == 1
    assert results[0]["output"] == []


def test_list_result_degrades_to_empty_turn():
    # Loop returns a list instead of a dict: base dies the same way.
    ag = make_agent(["not", "a", "dict"])
    results = run_all(ag)
    assert len(results) == 1
    assert results[0]["output"] == []


def test_non_dict_partial_items_skipped():
    # Partial items containing non-dict entries: base dies on pi.get;
    # fixed code skips them. Dict entries still flow through. The trailing
    # assistant message keeps the run-loop head check on a dict (that
    # non-dict-head hardening lives on sibling branch
    # muse/run-loop-malformed-message-hardening).
    mixed = [
        {"type": "computer_call_output", "call_id": "c1", "output": {}},
        "junk-string",
        42,
        ASSISTANT_MSG,
    ]
    ag = make_agent({"output": [ASSISTANT_MSG], "usage": {}}, handle_item_result=mixed)
    results = run_all(ag)
    assert len(results) == 2  # step result + partial yield
    partial = results[1]["output"]
    assert partial == mixed  # items are passed through, malformed ones skipped in scan


def test_well_formed_output_passes_through():
    # Control: normal step output is untouched by the hardening.
    ag = make_agent({"output": [ASSISTANT_MSG], "usage": {"prompt_tokens": 1}})
    results = run_all(ag)
    assert len(results) == 1
    assert results[0]["output"] == [ASSISTANT_MSG]


def test_missing_output_key_passes_through():
    # Control: result without "output" at all still yields an empty turn.
    ag = make_agent({"usage": {}})
    results = run_all(ag)
    assert len(results) == 1
    assert results[0]["output"] == []


if __name__ == "__main__":
    tests = [
        test_non_list_output_degrades_to_empty_turn,
        test_non_dict_result_degrades_to_empty_turn,
        test_list_result_degrades_to_empty_turn,
        test_non_dict_partial_items_skipped,
        test_well_formed_output_passes_through,
        test_missing_output_key_passes_through,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
