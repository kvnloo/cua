"""Minimal JSON Schema (draft 2020-12 subset) validator for the evaluator's own schemas.

Supports: type, required, properties, additionalProperties (bool), enum, const, items,
minimum, maximum, exclusiveMinimum, minItems, pattern, $ref to #/$defs/<name>.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schema"
_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list, "null": type(None)}


def load(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _type_ok(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[t])


def validate(value: Any, schema: dict[str, Any], root: dict[str, Any] | None = None, at: str = "$") -> list[str]:
    root = root or schema
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return validate(value, root["$defs"][name], root, at)
    errors: list[str] = []
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(_type_ok(value, t) for t in types):
            return [f"{at}: expected {types}, got {type(value).__name__}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{at}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{at}: {value!r} not in {schema['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{at}: {value} < {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{at}: {value} > {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{at}: {value} <= {schema['exclusiveMinimum']}")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{at}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{at}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errors.extend(validate(item, schema["items"], root, f"{at}[{i}]"))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{at}: missing {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors.extend(validate(item, props[key], root, f"{at}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{at}: unexpected {key}")
    return errors
