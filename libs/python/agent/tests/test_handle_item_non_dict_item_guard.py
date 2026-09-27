"""Non-dict items must not crash _handle_item.

``ComputerAgent._handle_item`` opened with ``call_id = item.get("call_id")``.
A non-dict entry in the run loop's output list (bare string/number from
malformed model output) raised AttributeError before any type dispatch, and
only ToolError is caught further down — so the AttributeError escaped and
killed the whole run.

Fix: non-dict items are skipped up front; dict handling is unchanged.
"""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1] / "cua_agent"


def _mod(name, path=None, **attrs):
    m = types.ModuleType(name)
    if path is not None:
        m.__path__ = path
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _factory(name):
    return type(name, (dict,), {"__init__": lambda self, **kw: dict.__init__(self, kw)})


def _install_stubs():
    class BaseModel:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def _deco(*a, **k):
        def wrap(f):
            return f

        return wrap

    _mod("pydantic", BaseModel=BaseModel, field_validator=_deco,
         model_validator=_deco)

    litellm = _mod("litellm", path=[], ResponseInputParam=dict,
                   ResponsesAPIResponse=dict, ToolParam=dict)
    _mod("litellm.utils", path=[])
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)
    _mod("litellm.types", path=[])
    _mod("litellm.types.utils", path=[], ModelResponse=dict)
    litellm.utils = sys.modules["litellm.utils"]

    _mod("cua_core", path=[])
    _mod("cua_core.telemetry", path=[], is_telemetry_enabled=lambda: False,
         record_event=lambda *a, **k: None)

    _mod("openai", path=[])
    _mod("openai.types", path=[])
    _mod("openai.types.responses", path=[])
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam",
    ]
    for mod, names in {
        "easy_input_message_param": ["EasyInputMessageParam"],
        "response_computer_tool_call_param": action_names,
        "response_function_tool_call_param": ["ResponseFunctionToolCallParam"],
        "response_input_image_param": ["ResponseInputImageParam"],
        "response_output_message_param": ["ResponseOutputMessageParam"],
        "response_output_text_param": ["ResponseOutputTextParam"],
        "response_reasoning_item_param": ["ResponseReasoningItemParam", "Summary"],
    }.items():
        _mod(f"openai.types.responses.{mod}",
             **{n: _factory(n) for n in names})


def _pkg(name, path):
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    sys.modules[name] = m
    return m


def _load(dotted, path):
    spec = importlib.util.spec_from_file_location(dotted, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = m
    spec.loader.exec_module(m)
    return m


def _load_agent():
    for key in [k for k in sys.modules if k == "cua_agent"
                or k.startswith(("cua_agent.", "pydantic", "litellm", "openai",
                                 "cua_core"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _mod("cua_agent.adapters", path=[],
         AzureMLAdapter=object, CUAAdapter=object,
         HuggingFaceLocalAdapter=object, HumanAdapter=object,
         MLXVLMAdapter=object)
    _mod("cua_agent.callbacks", path=[],
         BudgetManagerCallback=object, ImageRetentionCallback=object,
         LoggingCallback=object, OperatorNormalizerCallback=object,
         OtelCallback=object, PromptInstructionsCallback=object,
         TelemetryCallback=object, TrajectorySaverCallback=object)
    _mod("cua_agent.computers", path=[],
         AsyncComputerHandler=object, is_agent_computer=lambda x: False,
         make_computer_handler=lambda *a, **k: None)
    _pkg("cua_agent.tools", base + "/tools")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.responses", base + "/responses.py")
    _load("cua_agent.tools.base", base + "/tools/base.py")
    return _load("cua_agent.agent", base + "/agent.py")


ag = _load_agent()

agent = ag.ComputerAgent.__new__(ag.ComputerAgent)
agent.callbacks = []
agent.telemetry_enabled = False
agent.screenshot_delay = 0


class _Computer:
    pass


def handle(item):
    return asyncio.run(
        agent._handle_item(item, computer=_Computer(), ignore_call_ids=None)
    )


def test_string_item_skipped():
    assert handle("raw-model-output") == []


def test_int_item_skipped():
    assert handle(42) == []


def test_list_item_skipped():
    assert handle(["not", "a", "dict"]) == []


def test_none_item_skipped():
    assert handle(None) == []


def test_dict_item_still_handled():
    # A message-type dict item returns [] through the normal path.
    assert handle({"type": "message", "call_id": "c1"}) == []
