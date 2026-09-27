"""Tests: ComputerAgent._process_input accepts a single message dict.

_process_input iterated its input unconditionally (after the str special
case). Passing a single message dict instead of a one-element list iterated
the dict's *keys*, producing ["role", "content"] — a list of strings that
crashed the run loop later with a cryptic AttributeError (msg.get on str)
instead of running the intended prompt.

A single message dict is now wrapped as a one-message list. str and
list-of-dict inputs are unchanged.

Self-contained: get_json and _process_input are extracted from
cua_agent/agent.py by AST (the module's litellm/openai imports are not
available in this sandbox); only typing/json names are provided.
"""

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PATH = Path(__file__).resolve().parents[1] / "cua_agent" / "agent.py"


def _load_process_input():
    src = PATH.read_text()
    tree = ast.parse(src)
    (get_json_fn,) = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_json"
    ]
    (cls,) = [
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ComputerAgent"
    ]
    (process_input_fn,) = [
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef) and n.name == "_process_input"
    ]
    ns: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "Set": Set,
        "Messages": Any,  # annotation only; evaluated at def time
        "json": json,
    }
    exec(
        compile(ast.Module(body=[get_json_fn, process_input_fn], type_ignores=[]), str(PATH), "exec"),
        ns,
    )
    return ns["_process_input"]


_process_input = _load_process_input()


class TestSingleDict:
    def test_single_message_dict_wrapped(self):
        out = _process_input(None, {"role": "user", "content": "hi"})
        assert out == [{"role": "user", "content": "hi"}]

    def test_single_dict_passes_through_get_json(self):
        out = _process_input(None, {"role": "user", "content": [{"type": "text", "text": "hi"}]})
        assert out == [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    def test_single_dict_does_not_iterate_keys(self):
        out = _process_input(None, {"role": "user", "content": "hi"})
        assert all(isinstance(m, dict) for m in out)


class TestUnchangedInputs:
    def test_string_input(self):
        assert _process_input(None, "hello") == [{"role": "user", "content": "hello"}]

    def test_list_of_dicts(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert _process_input(None, msgs) == msgs

    def test_empty_list(self):
        assert _process_input(None, []) == []
