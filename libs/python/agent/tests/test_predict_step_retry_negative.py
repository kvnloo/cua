"""Red/green tests: _predict_step_with_retry must tolerate negative max_retries.

ComputerAgent accepts max_retries as an int with no validation, and
_predict_step_with_retry looped ``range(max_retries + 1)``. A negative value
(e.g. max_retries=-1) ran zero attempts, fell through to ``raise last_exc``
with last_exc still None, and surfaced as
``TypeError: exceptions must derive from BaseException`` — a confusing crash
for a simple misconfiguration, and predict_step never even ran.

The fix clamps negative values to 0 (one attempt, no retries), matching the
existing None -> 0 handling.

Self-contained: loads only the _predict_step_with_retry and _is_retryable_error
functions from agent.py by AST extraction (no litellm or package imports).
"""

import asyncio
import ast
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parent.parent / "cua_agent" / "agent.py"


def _load_funcs():
    src = AGENT_PATH.read_text()
    tree = ast.parse(src)
    wanted = {"_is_retryable_error", "_predict_step_with_retry"}
    parts = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
    assert len(parts) == 2, "expected both helpers in agent.py"
    ns = {"asyncio": asyncio, "random": __import__("random"), "Optional": __import__("typing").Optional,
          "Any": __import__("typing").Any, "BaseException": BaseException}
    # _is_retryable_error references litellm.exceptions lazily inside try/except
    exec(compile(ast.Module(body=parts, type_ignores=[]), str(AGENT_PATH), "exec"), ns)
    return ns["_predict_step_with_retry"]


_predict_step_with_retry = _load_funcs()


class FakeLoop:
    def __init__(self, fail_times=0):
        self.calls = 0
        self.fail_times = fail_times

    async def predict_step(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError("simulated transient timeout")
        return {"output": [], "usage": {}}


def test_negative_max_retries_runs_one_attempt():
    loop = FakeLoop()
    result = asyncio.run(
        _predict_step_with_retry(loop, {"messages": []}, hooks={}, max_retries=-1, base_delay=0)
    )
    assert result == {"output": [], "usage": {}}
    assert loop.calls == 1, f"expected exactly 1 attempt, got {loop.calls}"


def test_zero_max_retries_runs_one_attempt():
    loop = FakeLoop()
    result = asyncio.run(
        _predict_step_with_retry(loop, {"messages": []}, hooks={}, max_retries=0, base_delay=0)
    )
    assert result == {"output": [], "usage": {}}
    assert loop.calls == 1


def test_positive_max_retries_still_retries():
    loop = FakeLoop(fail_times=2)
    result = asyncio.run(
        _predict_step_with_retry(loop, {"messages": []}, hooks={}, max_retries=2, base_delay=0)
    )
    assert result == {"output": [], "usage": {}}
    assert loop.calls == 3, f"expected 3 attempts, got {loop.calls}"


def test_none_max_retries_runs_one_attempt():
    loop = FakeLoop()
    result = asyncio.run(
        _predict_step_with_retry(loop, {"messages": []}, hooks={}, max_retries=None, base_delay=0)
    )
    assert result == {"output": [], "usage": {}}
    assert loop.calls == 1


if __name__ == "__main__":
    test_negative_max_retries_runs_one_attempt()
    print("PASS test_negative_max_retries_runs_one_attempt")
    test_zero_max_retries_runs_one_attempt()
    print("PASS test_zero_max_retries_runs_one_attempt")
    test_positive_max_retries_still_retries()
    print("PASS test_positive_max_retries_still_retries")
    test_none_max_retries_runs_one_attempt()
    print("PASS test_none_max_retries_runs_one_attempt")
