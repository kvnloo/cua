"""Tests: _process_input rejects unsupported shapes with a clear error.

ComputerAgent._process_input treated anything that was not a string as a
list of messages. A None or int input raised a bare TypeError
("'NoneType' object is not iterable") from deep in the list
comprehension, and a single message dict passed without its enclosing
list was silently mangled into a list of its keys (['role',
'content']) — a confusing failure far from the caller's mistake.

Now: a lone dict is wrapped as a single message, other iterables
(lists, tuples, generators) still work, and unsupported inputs (None,
int, bytes) raise ValueError naming the expected shapes.

Self-contained: _process_input and get_json are extracted from agent.py
by AST and exec'd standalone (the sandbox lacks litellm).
"""

import ast
import json
import os
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Set

import pytest


def _load_fn():
    path = os.path.join(os.path.dirname(__file__), "..", "cua_agent", "agent.py")
    tree = ast.parse(open(path).read())
    get_json = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "get_json"
    )
    target = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_process_input"
    )
    target.args.args = [a for a in target.args.args if a.arg != "self"]
    for node in ast.walk(target):
        if isinstance(node, ast.arg):
            node.annotation = None
    target.returns = None
    ns: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "Set": Set,
        "Iterable": Iterable,
        "json": json,
    }
    exec(
        compile(ast.Module(body=[get_json, target], type_ignores=[]), path, "exec"),
        ns,
    )
    return ns["_process_input"]


_process_input = _load_fn()


class TestProcessInputShapes:
    def test_str_becomes_single_user_message(self):
        assert _process_input("hi") == [{"role": "user", "content": "hi"}]

    def test_list_of_dicts_unchanged(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert _process_input(msgs) == msgs

    def test_tuple_of_dicts_accepted(self):
        assert _process_input(({"role": "user", "content": "hi"},)) == [
            {"role": "user", "content": "hi"}
        ]

    def test_lone_dict_wrapped_as_single_message(self):
        assert _process_input({"role": "user", "content": "hi"}) == [
            {"role": "user", "content": "hi"}
        ]

    def test_generator_accepted(self):
        gen = ({"role": "user", "content": "hi"} for _ in range(1))
        assert _process_input(gen) == [{"role": "user", "content": "hi"}]

    def test_none_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a string"):
            _process_input(None)

    def test_int_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a string"):
            _process_input(42)

    def test_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="must be a string"):
            _process_input(b"hi")

    def test_error_names_received_type(self):
        with pytest.raises(ValueError, match="NoneType"):
            _process_input(None)
