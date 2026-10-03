"""B-05 caller-side variants for Phase B (MEASUREMENT HARNESS ONLY, caller side).

Registered here; an arm uses one only when PREREG-AMENDMENT-1.json names it. The default variants
are the library behaviour, exactly.

* parser ``fast`` (c_out.parse): a response line that is exactly a JSON-RPC success envelope
  {"jsonrpc": "2.0", "id": <int (not bool) | str>, "result": <object>} is decoded with the stdlib
  json module and wrapped with ``model_construct`` (the same field values the library's validation
  produces for this shape); every other line, and every line json.loads rejects, goes through the
  library parser unchanged (same result, same exception). CallToolResult validation and the
  output-schema validation still run on the result.
* validator ``fast`` (c_out.validate): each tool output schema is compiled at tools/list time
  (outside T) into closures for the keywords the Driver's schemas use (type, enum, const, properties,
  required, additionalProperties, items, anyOf, oneOf, minimum, maximum; format and description are
  annotations for a validator built without a format checker). A schema with any other keyword keeps
  the jsonschema validator. ``iter_errors`` yields nothing when the closure accepts, and otherwise
  delegates to the jsonschema validator, so acceptance and the error text are the library's.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import mcp.types as types
from jsonschema._utils import equal as js_equal

import b05_stdio as bs

# ── parser ───────────────────────────────────────────────────────────────────
_ENVELOPE = frozenset(("jsonrpc", "id", "result"))


def fast_parse(line: str) -> types.JSONRPCMessage:
    try:
        obj = json.loads(line)
    except ValueError:
        return bs.default_parse(line)
    if (type(obj) is dict and obj.keys() == _ENVELOPE and obj["jsonrpc"] == "2.0"
            and (type(obj["id"]) is int or type(obj["id"]) is str) and type(obj["result"]) is dict):
        return types.JSONRPCMessage(types.JSONRPCResponse.model_construct(
            jsonrpc="2.0", id=obj["id"], result=obj["result"]))
    return bs.default_parse(line)


bs.PARSERS["fast"] = fast_parse

# ── validator ────────────────────────────────────────────────────────────────
SUPPORTED = {"type", "enum", "const", "properties", "required", "additionalProperties", "items", "anyOf",
             "oneOf", "minimum", "maximum", "format", "description", "title"}


class Unsupported(Exception):
    pass


def _is_number(x: Any) -> bool:
    return (type(x) is int or type(x) is float) and type(x) is not bool


TYPE_CHECK: dict[str, Callable[[Any], bool]] = {
    "string": lambda x: type(x) is str,
    "integer": lambda x: (type(x) is int) or (type(x) is float and x.is_integer()),
    "number": lambda x: type(x) is int or type(x) is float,
    "boolean": lambda x: type(x) is bool,
    "null": lambda x: x is None,
    "object": lambda x: type(x) is dict,
    "array": lambda x: type(x) is list,
}


def compile_schema(schema: Any) -> Callable[[Any], bool]:
    """Closure returning True iff ``schema`` accepts the instance (Draft 2020-12 semantics for the
    supported keywords, jsonschema's type and equality rules). Raises Unsupported otherwise."""
    if schema is True:
        return lambda x: True
    if schema is False:
        return lambda x: False
    if not isinstance(schema, dict):
        raise Unsupported(repr(schema)[:40])
    extra = set(schema) - SUPPORTED
    if extra:
        raise Unsupported(",".join(sorted(extra)))
    checks: list[Callable[[Any], bool]] = []
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        fns = [TYPE_CHECK[t] for t in ts]
        checks.append(lambda x, fns=fns: any(f(x) for f in fns))
    if "enum" in schema:
        options = list(schema["enum"])
        checks.append(lambda x, o=options: any(js_equal(x, v) for v in o))
    if "const" in schema:
        c = schema["const"]
        checks.append(lambda x, c=c: js_equal(x, c))
    if "minimum" in schema:
        m = schema["minimum"]
        checks.append(lambda x, m=m: not _is_number(x) or x >= m)
    if "maximum" in schema:
        m = schema["maximum"]
        checks.append(lambda x, m=m: not _is_number(x) or x <= m)
    props = {k: compile_schema(v) for k, v in (schema.get("properties") or {}).items()}
    if props:
        checks.append(lambda x, p=props: type(x) is not dict or all(f(x[k]) for k, f in p.items() if k in x))
    if "required" in schema:
        req = list(schema["required"])
        checks.append(lambda x, req=req: type(x) is not dict or all(k in x for k in req))
    if "additionalProperties" in schema:
        known = set((schema.get("properties") or {}).keys())
        ap = compile_schema(schema["additionalProperties"])
        checks.append(lambda x, known=known, ap=ap: type(x) is not dict
                      or all(ap(v) for k, v in x.items() if k not in known))
    if "items" in schema:
        it = compile_schema(schema["items"])
        checks.append(lambda x, it=it: type(x) is not list or all(it(v) for v in x))
    if "anyOf" in schema:
        subs = [compile_schema(s) for s in schema["anyOf"]]
        checks.append(lambda x, subs=subs: any(f(x) for f in subs))
    if "oneOf" in schema:
        subs = [compile_schema(s) for s in schema["oneOf"]]
        checks.append(lambda x, subs=subs: sum(1 for f in subs if f(x)) == 1)
    return lambda x, checks=checks: all(c(x) for c in checks)


class FastValidator:
    """Wraps a compiled jsonschema validator: fast accept, library path for every rejection."""

    def __init__(self, library_validator: Any, schema: Any) -> None:
        self.library = library_validator
        self.accept = compile_schema(schema)

    def iter_errors(self, instance: Any):  # noqa: ANN201
        if self.accept(instance):
            return iter(())
        return self.library.iter_errors(instance)


def fast_validators(compiled: dict[str, Any], schemas: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Replace each compiled validator by a FastValidator where the schema is supported."""
    out, kept = {}, []
    for key, validator in compiled.items():
        try:
            out[key] = FastValidator(validator, schemas[key])
        except Unsupported as error:
            out[key] = validator
            kept.append(f"{key[:12]}:{error}")
    return out, kept
