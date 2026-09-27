"""Red/green harness for the lifecycle-hook exception isolation fix.

Loads the REAL agent.py from the worktree with the cua_agent package graph
stubbed (litellm, adapters, callbacks, computers, ...). Exercises every
lifecycle dispatcher with a raising callback followed by a recording callback:
on the fixed code the recording callback still runs and nothing propagates;
on base the first raise escapes.
"""
import asyncio
import importlib.util
import sys
import types

WT = "/home/hatch/workspace/scratch/cua-wt-muse-c59"  # replaced at publish time if needed
AGENT_SRC = WT + "/libs/python/agent/cua_agent/agent.py"


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def load_agent():
    # Wipe any previous load so red-on-base re-runs reload the file.
    for m in [m for m in sys.modules if m == "cua_agent" or m.startswith("cua_agent.")]:
        del sys.modules[m]

    _stub("litellm")
    _stub("litellm.utils")
    _stub("litellm.responses")
    _stub("litellm.responses.utils", Usage=type("Usage", (), {}))
    _stub("cua_core")
    _stub("cua_core.telemetry", is_telemetry_enabled=lambda: False,
          record_event=lambda *a, **k: None)

    pkg = types.ModuleType("cua_agent")
    pkg.__path__ = [WT + "/libs/python/agent/cua_agent"]
    sys.modules["cua_agent"] = pkg

    class _C:
        pass

    _stub("cua_agent.adapters", AzureMLAdapter=_C, CUAAdapter=_C,
          HuggingFaceLocalAdapter=_C, HumanAdapter=_C, MLXVLMAdapter=_C)
    _stub("cua_agent.callbacks", BudgetManagerCallback=_C, ImageRetentionCallback=_C,
          LoggingCallback=_C, OperatorNormalizerCallback=_C, OtelCallback=_C,
          PromptInstructionsCallback=_C, TelemetryCallback=_C, TrajectorySaverCallback=_C)
    _stub("cua_agent.computers", AsyncComputerHandler=_C,
          is_agent_computer=lambda t: False,
          make_computer_handler=lambda s: None)
    _stub("cua_agent.decorators", find_agent_config=lambda *a, **k: None)
    _stub("cua_agent.responses",
          make_tool_error_item=lambda *a, **k: {},
          replace_failed_computer_calls_with_function_calls=lambda m: m)
    _stub("cua_agent.tools")
    _stub("cua_agent.tools.base", BaseComputerTool=_C, BaseTool=_C)
    _stub("cua_agent.types", AgentCapability=str, IllegalArgumentError=Exception,
          Messages=list, ToolError=Exception)

    spec = importlib.util.spec_from_file_location("cua_agent.agent", AGENT_SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cua_agent.agent"] = mod
    spec.loader.exec_module(mod)
    return mod


class Boom(Exception):
    pass


class Raising:
    """Callback whose every hook raises."""

    def __getattr__(self, name):
        if name.startswith("on_"):
            async def _raise(*a, **k):
                raise Boom(f"boom in {name}")
            return _raise
        raise AttributeError(name)


class Recorder:
    """Callback recording every hook invocation."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("on_"):
            async def _rec(*a, **k):
                self.calls.append(name)
                if name == "on_run_continue":
                    return self.verdict
                if name in ("on_llm_start", "on_llm_end"):
                    return None  # "no change"
                return None
            return _rec
        raise AttributeError(name)


def make_agent(callbacks):
    mod = sys.modules["cua_agent.agent"]
    agent = object.__new__(mod.ComputerAgent)
    agent.callbacks = callbacks
    return agent


CASES = [
    # (dispatcher, args, hook-name-recorded)
    ("_on_run_start", ({"m": 1}, []), "on_run_start"),
    ("_on_run_end", ({"m": 1}, [], []), "on_run_end"),
    ("_on_api_start", ({"model": "x"},), "on_api_start"),
    ("_on_api_end", ({"model": "x"}, {"output": []}), "on_api_end"),
    ("_on_usage", ({"t": 1},), "on_usage"),
    ("_on_screenshot", ("aGVsbG8=", "shot"), "on_screenshot"),
    ("_on_text", ({"type": "message"},), "on_text"),
    ("_on_responses", ({"m": 1}, {"output": []}), "on_responses"),
    ("_on_computer_call_start", ({"type": "computer_call"},), "on_computer_call_start"),
    ("_on_computer_call_end", ({"type": "computer_call"}, []), "on_computer_call_end"),
    ("_on_function_call_start", ({"type": "function_call"},), "on_function_call_start"),
    ("_on_function_call_end", ({"type": "function_call"}, []), "on_function_call_end"),
]


async def run_case(dispatcher, args, hook):
    rec = Recorder()
    agent = make_agent([Raising(), rec])
    try:
        await getattr(agent, dispatcher)(*args)
    except Boom:
        return False, f"{dispatcher}: Boom escaped (base behavior)"
    except Exception as e:
        return False, f"{dispatcher}: unexpected {type(e).__name__}: {e}"
    if hook not in rec.calls:
        return False, f"{dispatcher}: later callback never ran (calls={rec.calls})"
    return True, f"{dispatcher}: isolated, later callback ran"


async def run_specials():
    results = []

    # _on_run_continue: raising callback abstains, explicit False still vetoes.
    rec = Recorder()
    rec.verdict = True
    agent = make_agent([Raising(), rec])
    try:
        ok = await agent._on_run_continue({}, [], [])
        results.append((ok is True, "_on_run_continue: raising callback abstains -> True"))
    except Boom:
        results.append((False, "_on_run_continue: Boom escaped"))

    rec2 = Recorder()
    rec2.verdict = False
    agent2 = make_agent([Raising(), rec2])
    try:
        ok = await agent2._on_run_continue({}, [], [])
        results.append((ok is False, "_on_run_continue: explicit False veto respected"))
    except Boom:
        results.append((False, "_on_run_continue: Boom escaped on veto path"))

    # _on_llm_start: raising callback leaves messages intact.
    msgs = [{"role": "user", "content": "hi"}]
    agent3 = make_agent([Raising()])
    try:
        out = await agent3._on_llm_start(msgs)
        results.append((out == msgs, "_on_llm_start: raising callback keeps messages"))
    except Boom:
        results.append((False, "_on_llm_start: Boom escaped"))

    # _on_llm_end: None return means no change (guarded), raise is skipped.
    agent4 = make_agent([Raising(), Recorder()])
    try:
        out = await agent4._on_llm_end(msgs)
        results.append((out == msgs, "_on_llm_end: raise skipped, None kept"))
    except Boom:
        results.append((False, "_on_llm_end: Boom escaped"))
    return results


async def main():
    load_agent()
    results = []
    for dispatcher, args, hook in CASES:
        results.append(await run_case(dispatcher, args, hook))
    results.extend(await run_specials())
    n_fail = 0
    for ok, label in results:
        print(("PASS" if ok else "FAIL"), "-", label)
        n_fail += not ok
    print(f"{len(results) - n_fail}/{len(results)} green")
    return n_fail


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
