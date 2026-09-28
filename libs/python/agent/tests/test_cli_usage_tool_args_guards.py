"""Tests: cli chat_loop tolerates non-dict usage; _verify_json_format_args rejects non-dict JSON.

cli.py chat_loop does `result.get("usage", {}).get("response_cost", 0)`, but
agent.run() yields a litellm Usage object (no .get) — not a dict — on every
partial yield (agent.py yields {"output": partial_items, "usage": Usage(...)}
whenever _handle_item produces partial items, i.e. on each executed computer
action). With --usage, the first computer action killed the CLI with
AttributeError. A usage dict carrying response_cost=None poisoned total_cost
to None, crashing the next `$...:.2f` format. Usage extraction now handles
non-dict usage objects and None costs.

Separately, BaseTool._verify_json_format_args returned whatever json.loads
produced, typed as dict: a model emitting function_call arguments as a JSON
array/string (agent.py: `args = json.loads(item.get("arguments"))` is raw
model output) sailed through the required-field membership check — which
works on lists/strings — and crashed downstream at params_dict.get(...).
Non-dict parsed params now raise ValueError.
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
AGENT_DIR = REPO / "libs/python/agent/cua_agent"
CLI_FILE = AGENT_DIR / "cli.py"
TOOLS_BASE_FILE = AGENT_DIR / "tools" / "base.py"


# ---------------------------------------------------------------------------
# Module loading (standalone: cli.py must not import litellm; stub dotenv/yaspin)
# ---------------------------------------------------------------------------


class _DummySpinner:
    def __init__(self, *args, **kwargs):
        self.text = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def hide(self):
        pass

    def show(self):
        pass


def _load_cli():
    for name in ("dotenv", "yaspin", "c72_cli"):
        sys.modules.pop(name, None)

    dotenv_mod = types.ModuleType("dotenv")
    dotenv_mod.load_dotenv = lambda *a, **k: None
    sys.modules["dotenv"] = dotenv_mod

    yaspin_mod = types.ModuleType("yaspin")
    yaspin_mod.yaspin = lambda *a, **k: _DummySpinner()
    sys.modules["yaspin"] = yaspin_mod

    spec = importlib.util.spec_from_file_location("c72_cli", CLI_FILE)
    cli = importlib.util.module_from_spec(spec)
    sys.modules["c72_cli"] = cli
    spec.loader.exec_module(cli)
    return cli


def _load_tools_base():
    sys.modules.pop("c72_tools_base", None)
    spec = importlib.util.spec_from_file_location("c72_tools_base", TOOLS_BASE_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["c72_tools_base"] = mod
    spec.loader.exec_module(mod)
    return mod


class _NonDictUsage:
    """Mimics litellm.responses.utils.Usage: attribute access, no .get()."""

    def __init__(self, response_cost=None):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        if response_cost is not None:
            self.response_cost = response_cost


class _FakeAgent:
    """Yields configured results on each run() call."""

    def __init__(self, results):
        self._results = results
        self.calls = 0
        self.agent_config_info = types.SimpleNamespace(
            agent_class=type("FakeLoop", (), {})
        )

    async def run(self, history):
        self.calls += 1
        for r in self._results:
            yield r


async def _fake_ainput(prompt=""):
    # chat_loop prompts for the next user turn after the agent responds.
    return "exit"


def _run_chat_loop(cli, results, show_usage=True):
    agent = _FakeAgent(results)
    orig_ainput = cli.ainput
    cli.ainput = _fake_ainput
    try:
        # initial_prompt="go" so the first iteration runs the agent; the
        # follow-up user prompt then answers "exit" to end the loop.
        asyncio.run(cli.chat_loop(agent, "model", "container", "go", show_usage))
    finally:
        cli.ainput = orig_ainput
    return agent


def _message_output(text="hi"):
    return [{"type": "message", "role": "assistant", "content": [{"text": text}]}]


# ---------------------------------------------------------------------------
# cli.py chat_loop usage guards
# ---------------------------------------------------------------------------


def test_chat_loop_survives_non_dict_usage_on_partial_yield():
    """Partial yields carry usage as a litellm Usage object (no .get)."""
    cli = _load_cli()
    result = {"output": _message_output(), "usage": _NonDictUsage()}
    # Pre-fix: AttributeError: '_NonDictUsage' object has no attribute 'get'
    _run_chat_loop(cli, [result], show_usage=True)


def test_chat_loop_survives_none_response_cost():
    """usage dict with response_cost=None must not poison total_cost."""
    cli = _load_cli()
    result = {"output": _message_output(), "usage": {"response_cost": None}}
    # Pre-fix: TypeError (0 + None), or later on the $...:.2f format
    _run_chat_loop(cli, [result], show_usage=True)


def test_chat_loop_still_accumulates_dict_usage_cost():
    """Dict usage with a numeric response_cost keeps accumulating (no regression)."""
    cli = _load_cli()
    results = [
        {"output": _message_output("one"), "usage": {"response_cost": 0.25}},
        {"output": _message_output("two"), "usage": {"response_cost": 0.25}},
    ]
    agent = _FakeAgent(results)

    printed = []
    orig_print_colored = cli.print_colored

    def spy_print_colored(text, *args, **kwargs):
        printed.append(text)
        return orig_print_colored(text, *args, **kwargs)

    cli.print_colored = spy_print_colored
    orig_ainput = cli.ainput
    cli.ainput = _fake_ainput
    try:
        asyncio.run(cli.chat_loop(agent, "model", "container", "go", True))
    finally:
        cli.print_colored = orig_print_colored
        cli.ainput = orig_ainput

    totals = [t for t in printed if t.startswith("Total cost:")]
    assert totals == ["Total cost: $0.50"], totals


def test_chat_loop_usage_absent_ok():
    """Results without a usage key keep working."""
    cli = _load_cli()
    _run_chat_loop(cli, [{"output": _message_output()}], show_usage=True)


# ---------------------------------------------------------------------------
# tools/base.py _verify_json_format_args guards
# ---------------------------------------------------------------------------


def _make_tool(mod):
    class T(mod.BaseTool):
        name = "t"

        @property
        def description(self):
            return "t"

        @property
        def parameters(self):
            return {
                "type": "object",
                "properties": {"a": {"type": "string"}},
            }

        def call(self, params, **kwargs):
            return {}

    return T()


def test_verify_json_format_args_rejects_json_array():
    """Model emitting arguments as a JSON array must not pass as a params dict."""
    mod = _load_tools_base()
    tool = _make_tool(mod)
    # Pre-fix: returned the list unchanged (typed as dict); downstream
    # params_dict.get("action") then raised AttributeError.
    with pytest.raises(ValueError, match="JSON object"):
        tool._verify_json_format_args('["a", 1]')


def test_verify_json_format_args_rejects_json_string():
    mod = _load_tools_base()
    tool = _make_tool(mod)
    with pytest.raises(ValueError, match="JSON object"):
        tool._verify_json_format_args('"abc"')


def test_verify_json_format_args_rejects_json_number():
    mod = _load_tools_base()
    tool = _make_tool(mod)
    with pytest.raises(ValueError, match="JSON object"):
        tool._verify_json_format_args("42")


def test_verify_json_format_args_rejects_non_dict_param():
    """A non-str, non-dict params value (e.g. list straight from the caller)."""
    mod = _load_tools_base()
    tool = _make_tool(mod)
    with pytest.raises(ValueError, match="JSON object"):
        tool._verify_json_format_args(["a"])


def test_verify_json_format_args_accepts_json_object_string():
    """Valid JSON object strings still parse (no regression)."""
    mod = _load_tools_base()
    tool = _make_tool(mod)
    assert tool._verify_json_format_args('{"a": "x"}') == {"a": "x"}


def test_verify_json_format_args_accepts_dict():
    mod = _load_tools_base()
    tool = _make_tool(mod)
    assert tool._verify_json_format_args({"a": "x"}) == {"a": "x"}


def test_verify_json_format_args_still_rejects_bad_json():
    mod = _load_tools_base()
    tool = _make_tool(mod)
    with pytest.raises(ValueError, match="valid JSON"):
        tool._verify_json_format_args("{bad json")
