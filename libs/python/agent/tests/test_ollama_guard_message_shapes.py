"""Malformed messages must not crash the Ollama image-input guard.

``ComputerAgent.run`` scans the pre-LLM messages for image content when the
model is an Ollama model. The scan called ``m.get("content")`` /
``m.get("type")`` / ``output.get(...)`` unguarded, so a non-dict message
(raw user input, or a malformed earlier step result carried into the next
iteration) raised ``AttributeError`` and killed the run. A non-dict
``computer_call_output`` output raised the same way.

Fix: the scan is now the module-level ``_message_has_image_content`` with
isinstance guards; non-dict messages/outputs simply report no image
content. Positive detection behavior is unchanged.
"""
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

    _mod("litellm", path=[],
         acompletion=None,
         aresponses=None,
         ResponseInputParam=dict,
         ResponsesAPIResponse=dict,
         ToolParam=dict)
    _mod("litellm.utils", path=[])
    _mod("litellm.responses", path=[])
    _mod("litellm.responses.utils", path=[], Usage=dict)

    _mod("cua_core", path=[])
    _mod("cua_core.telemetry", path=[],
         is_telemetry_enabled=lambda: False,
         record_event=lambda *a, **k: None)

    _mod("openai", path=[])
    _mod("openai.types", path=[])
    _mod("openai.types.responses", path=[])
    action_names = [
        "ActionClick", "ActionDoubleClick", "ActionDrag", "ActionDragPath",
        "ActionKeypress", "ActionMove", "ActionScreenshot", "ActionScroll",
        "ActionWait", "ActionType", "PendingSafetyCheck",
        "ResponseComputerToolCallParam", "EasyInputMessageParam",
        "ResponseInputImageParam", "ResponseOutputMessageParam",
        "ResponseOutputTextParam", "ResponseReasoningItemParam", "Summary",
        "ResponseFunctionToolCallParam",
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
             **{n: (lambda **kw: dict(kw)) for n in names})


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
                or k.startswith(("cua_agent.", "cua_core", "pydantic",
                                 "litellm", "openai"))]:
        del sys.modules[key]
    _install_stubs()
    base = str(REPO)
    _pkg("cua_agent", base)
    _pkg("cua_agent.loops", base + "/loops")

    adapters = _pkg("cua_agent.adapters", base + "/adapters")
    for n in ("AzureMLAdapter", "CUAAdapter", "HuggingFaceLocalAdapter",
              "HumanAdapter", "MLXVLMAdapter"):
        setattr(adapters, n, object)

    callbacks = _pkg("cua_agent.callbacks", base + "/callbacks")
    for n in ("BudgetManagerCallback", "ImageRetentionCallback",
              "LoggingCallback", "OperatorNormalizerCallback",
              "OtelCallback", "PromptInstructionsCallback",
              "TelemetryCallback", "TrajectorySaverCallback"):
        setattr(callbacks, n, object)

    computers = _pkg("cua_agent.computers", base + "/computers")
    for n in ("AsyncComputerHandler", "is_agent_computer",
              "make_computer_handler"):
        setattr(computers, n, object)

    _pkg("cua_agent.tools", base + "/tools")
    _load("cua_agent.types", base + "/types.py")
    _load("cua_agent.decorators", base + "/decorators.py")
    _load("cua_agent.responses", base + "/responses.py")
    _load("cua_agent.tools.base", base + "/tools/base.py")
    return _load("cua_agent.agent", base + "/agent.py")


ag = _load_agent()
has_image = ag._message_has_image_content


def test_non_dict_message_reports_no_image():
    for bad in ("oops", 42, None, ["x"]):
        assert has_image(bad) is False


def test_non_dict_output_reports_no_image():
    msg = {"type": "computer_call_output", "output": "not-a-dict"}
    assert has_image(msg) is False


def test_missing_output_reports_no_image():
    assert has_image({"type": "computer_call_output"}) is False


def test_image_url_content_detected():
    msg = {"role": "user",
           "content": [{"type": "text", "text": "hi"},
                       {"type": "image_url",
                        "image_url": {"url": "data:image/png;base64,xx"}}]}
    assert has_image(msg) is True


def test_computer_call_output_screenshot_detected():
    msg = {"type": "computer_call_output",
           "output": {"type": "input_image",
                      "image_url": "data:image/png;base64,xx"}}
    assert has_image(msg) is True


def test_plain_text_message_clean():
    assert has_image({"role": "user", "content": "hello"}) is False


def test_non_image_output_type_clean():
    msg = {"type": "computer_call_output",
           "output": {"type": "text", "text": "done"}}
    assert has_image(msg) is False
