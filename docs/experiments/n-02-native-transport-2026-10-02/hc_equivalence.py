#!/usr/bin/env python3
"""N-02 HC negative/unit control: the caller-compiled output validators must accept and reject
exactly what the mcp library path (jsonschema.validate) accepts and rejects.

Inputs (packaged raw): the first measured block's output schemas
(raw/<label>/output-schemas.json) and its corpus of full real structuredContent results
(raw/<label>/hc-corpus.jsonl.gz, rounds 0-1). Selection is deterministic: per tool, the first
results in corpus order up to a fixed quota (40 in total). Each real result also yields one
mutated result: mutation strategies are tried in a fixed order starting at (index mod the number of strategies that apply); the
first mutant that the reference path rejects is kept (40 invalid results).

Both paths are the exact code the arms run: the reference is
``mcp.ClientSession._validate_tool_result`` (library, jsonschema.validate), the candidate is the
harness's ``StampedClientSession._compiled_validate`` with validators compiled by
``compile_output_validators``. Required: identical accept/reject on 80/80.

Runs with the jev-use venv Python under hostless (no display, no Driver):
    hostless <venv-python> hc_equivalence.py --wt <worktree> --label n02-e01
writes hc-equivalence.json.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import gzip
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUOTA = {"get_window_state": 8, "click": 12, "set_value": 6, "list_windows": 6,
         "set_agent_cursor_motion": 4, "get_agent_cursor_state": 4}
WRONG = {"object": "n02-not-an-object", "array": "n02-not-an-array", "string": 12345, "integer": "n02-x",
         "number": "n02-x", "boolean": "n02-x", "null": "n02-x"}


def first_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The schema branch that describes the object's properties (anyOf/oneOf: first with properties)."""
    if "properties" in schema:
        return schema
    for key in ("anyOf", "oneOf", "allOf"):
        for branch in schema.get(key) or []:
            if isinstance(branch, dict) and "properties" in branch:
                return branch
    return schema


def mutants(value: dict[str, Any], schema: dict[str, Any]) -> list[tuple[str, Any]]:
    branch = first_object_schema(schema)
    props = branch.get("properties") or {}
    out: list[tuple[str, Any]] = []
    # 0: unknown top-level property
    m = copy.deepcopy(value)
    m["__n02_unexpected__"] = 1
    out.append(("add_unknown_property", m))
    # 1: drop a required property that is present
    req = [k for k in (branch.get("required") or []) if k in value]
    if req:
        m = copy.deepcopy(value)
        del m[req[0]]
        out.append((f"drop_required:{req[0]}", m))
    # 2: wrong type for the first present property with a simple declared type
    for key in sorted(value):
        t = (props.get(key) or {}).get("type")
        if isinstance(t, str) and t in WRONG:
            m = copy.deepcopy(value)
            m[key] = WRONG[t]
            out.append((f"wrong_type:{key}", m))
            break
    # 3: a present required property set to null. (The pre-registered "root_not_object" cannot be
    # built: mcp's CallToolResult requires structuredContent to be an object, so such a result never
    # reaches either validation path; deviation recorded in the README.)
    if req:
        m = copy.deepcopy(value)
        m[req[-1]] = None
        out.append((f"required_to_null:{req[-1]}", m))
    return out


async def outcome(fn, session: Any, tool: str, value: Any) -> tuple[bool, str]:
    from mcp import types

    result = types.CallToolResult(content=[], structuredContent=value, isError=False)
    try:
        await fn(session, tool, result)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - both paths raise RuntimeError on rejection
        return False, f"{type(exc).__name__}: {str(exc)[:200]}"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(Path(args.wt).resolve() / "libs/cua-driver/examples/jev-use/python"))
    from mcp import ClientSession

    import n02_harness

    cls = n02_harness.make_session_class(ClientSession)
    raw = HERE / "raw" / args.label
    schemas = json.loads((raw / "output-schemas.json").read_text(encoding="utf-8"))
    with gzip.open(raw / "hc-corpus.jsonl.gz", "rt", encoding="utf-8") as stream:
        corpus = [json.loads(x) for x in stream if x.strip()]
    picked: list[dict[str, Any]] = []
    counts = {k: 0 for k in QUOTA}
    for item in corpus:
        tool = item["tool"]
        if tool in QUOTA and counts[tool] < QUOTA[tool] and schemas.get(tool) is not None:
            counts[tool] += 1
            picked.append(item)
    session = object.__new__(cls)
    session._tool_output_schemas = dict(schemas)
    session.stamps = n02_harness.Stamps()
    compiled = session.compile_output_validators()

    async def reference(sess: Any, tool: str, result: Any) -> None:
        await ClientSession._validate_tool_result(sess, tool, result)

    async def candidate(sess: Any, tool: str, result: Any) -> None:
        await cls._compiled_validate(sess, tool, result)

    rows = []
    for i, item in enumerate(picked):
        tool, value = item["tool"], item["structuredContent"]
        cases = [("real", "none", value)]
        options = mutants(value, schemas[tool])
        chosen = None
        for k in range(len(options)):
            name, m = options[(i + k) % len(options)]
            ok, _ = await outcome(reference, session, tool, m)
            if not ok:
                chosen = (name, m)
                break
        if chosen is not None:
            cases.append(("mutant", chosen[0], chosen[1]))
        for case, mutation, v in cases:
            ref_ok, ref_msg = await outcome(reference, session, tool, v)
            cand_ok, cand_msg = await outcome(candidate, session, tool, v)
            rows.append({"i": i, "trial": item["trial"], "tool": tool, "case": case, "mutation": mutation,
                         "reference_accepts": ref_ok, "compiled_accepts": cand_ok, "agree": ref_ok == cand_ok,
                         "same_message": ref_msg == cand_msg, "reference_error": ref_msg[:160]})
    real = [r for r in rows if r["case"] == "real"]
    mut = [r for r in rows if r["case"] == "mutant"]
    summary = {
        "total": len(rows), "agree": sum(1 for r in rows if r["agree"]),
        "real": len(real), "real_accepted_by_reference": sum(1 for r in real if r["reference_accepts"]),
        "mutants": len(mut), "mutants_rejected_by_reference": sum(1 for r in mut if not r["reference_accepts"]),
        "mutants_rejected_by_compiled": sum(1 for r in mut if not r["compiled_accepts"]),
        "same_message": sum(1 for r in rows if r["same_message"]),
        "per_tool": counts, "compiled_validators": compiled,
        "mutation_kinds": sorted({r["mutation"].split(":")[0] for r in mut}),
    }
    return {"schema": "n02.hc_equivalence.v1", "label": args.label, "summary": summary, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", required=True)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    result = asyncio.run(run(args))
    (HERE / "hc-equivalence.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
