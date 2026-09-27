"""Tests: get_json tolerates non-JSON-safe dict keys in nested payloads.

custom_serializer preserved dict keys verbatim, then json.dumps blew up with
TypeError on non-primitive keys (e.g. tuple keys from structured tool
payloads). Since _process_input runs get_json on every input message, one
odd key killed the run before any LLM call. Non-primitive keys are now
coerced with str(); primitive keys round-trip exactly as json.dumps already
produced them (ints/floats/bools/None become strings on the loads round-trip,
unchanged behavior).
"""

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PATH = Path(__file__).resolve().parents[1] / "cua_agent" / "agent.py"


def _load_fn():
    src = PATH.read_text()
    tree = ast.parse(src)
    (fn,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "get_json"]
    ns: Dict[str, Any] = {
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "Set": Set,
        "json": json,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(PATH), "exec"), ns)
    return ns["get_json"]


get_json = _load_fn()


class TestTupleKeys:
    def test_tuple_key_coerced_not_crashed(self):
        out = get_json({"role": "user", "content": {(1, 2): "v"}})
        assert out == {"role": "user", "content": {"(1, 2)": "v"}}

    def test_nested_tuple_key(self):
        out = get_json({"a": {"b": {(0, 0): 1}}})
        assert out == {"a": {"b": {"(0, 0)": 1}}}

    def test_object_key_coerced(self):
        class K:
            def __str__(self):
                return "K!"

        out = get_json({K(): "v"})
        assert out == {"K!": "v"}


class TestPrimitiveKeysUnchanged:
    def test_int_key_roundtrip(self):
        # json.dumps already stringified int keys; behavior unchanged
        assert get_json({1: "a"}) == {"1": "a"}

    def test_none_key_roundtrip(self):
        assert get_json({None: "a"}) == {"null": "a"}

    def test_bool_key_roundtrip(self):
        assert get_json({True: "a"}) == {"true": "a"}

    def test_str_key_unchanged(self):
        assert get_json({"x": 1}) == {"x": 1}


class TestWellFormedUnchanged:
    def test_nested_payload(self):
        payload = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        assert get_json(payload) == payload

    def test_none_values_dropped(self):
        assert get_json({"a": None, "b": 1}) == {"b": 1}

    def test_circular_reference(self):
        d: Dict[str, Any] = {}
        d["self"] = d
        out = get_json(d)
        assert out == {"self": "<circular_reference:dict>"}
