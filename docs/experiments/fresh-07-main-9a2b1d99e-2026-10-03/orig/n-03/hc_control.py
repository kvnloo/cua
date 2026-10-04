#!/usr/bin/env python3
"""N-03 offline HC equivalence control (UNIT): the lazy per-schema caller-compiled validators (HCL)
must accept and reject exactly what the mcp library path (jsonschema.validate) accepts and rejects.

Lineage: N-02 hc_equivalence.py (same selection rule: a mutant enters the invalid corpus only if
the library path rejects it). N-03 needs 10 injected invalid outputs PER TOOL, so the mutation
strategies are enumerated per present key in a fixed order (PREREG.json controls.HC_equivalence_offline):
add_unknown_property, drop_required:<k>, wrong_type:<k>, required_to_null:<k>, enum_violation:<k>,
nested_wrong_type:<k>.<j>; real results are taken in corpus order and each yields its candidates
in that order; the first 10 distinct mutants per tool that the library rejects are kept.

Inputs (packaged raw): raw/runs/<label>/output-schemas.json and raw/runs/<label>/hc-corpus.jsonl(.gz)
of the measured k=1 blocks (rounds 0 and 12, X+HCL). Both paths are the code the arms run: the
reference is mcp.ClientSession._validate_tool_result; the candidate is the harness's
StampedClientSession._validate_tool_result with hcl=True (lazy compile at first use per schema).

Runs with the jev-use venv Python under hostless (no display, no Driver):
    hostless <venv-python> hc_control.py --wt <worktree> [--labels n03a2-a1 n03a2-a2]
writes hc-control.json.
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
TOOLS = ["list_windows", "set_agent_cursor_motion", "get_agent_cursor_state", "get_window_state", "set_value", "click"]
PER_TOOL = 10
WRONG = {"object": "n03-not-an-object", "array": "n03-not-an-array", "string": 12345, "integer": "n03-x",
         "number": "n03-x", "boolean": "n03-x", "null": "n03-x"}


def first_object_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if "properties" in schema:
        return schema
    for key in ("anyOf", "oneOf", "allOf"):
        for branch in schema.get(key) or []:
            if isinstance(branch, dict) and "properties" in branch:
                return branch
    return schema


def simple_type(prop: dict[str, Any]) -> str | None:
    t = prop.get("type")
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return non_null[0] if len(non_null) == 1 else None
    return None


def candidates(value: dict[str, Any], schema: dict[str, Any]) -> list[tuple[str, Any]]:
    branch = first_object_schema(schema)
    props = branch.get("properties") or {}
    present_req = [k for k in (branch.get("required") or []) if k in value]
    out: list[tuple[str, Any]] = []
    m = copy.deepcopy(value)
    m["__n03_unexpected__"] = 1
    out.append(("add_unknown_property", m))
    for k in present_req:
        m = copy.deepcopy(value)
        del m[k]
        out.append((f"drop_required:{k}", m))
    for k in sorted(value):
        t = simple_type(props.get(k) or {})
        if t in WRONG:
            m = copy.deepcopy(value)
            m[k] = WRONG[t]
            out.append((f"wrong_type:{k}", m))
    for k in present_req:
        m = copy.deepcopy(value)
        m[k] = None
        out.append((f"required_to_null:{k}", m))
    for k in sorted(value):
        enum = (props.get(k) or {}).get("enum")
        if isinstance(enum, list):
            m = copy.deepcopy(value)
            m[k] = "n03-not-in-enum"
            out.append((f"enum_violation:{k}", m))
    for k in sorted(value):
        sub = props.get(k) or {}
        if isinstance(value.get(k), dict) and isinstance(sub.get("properties"), dict):
            for j in sorted(value[k]):
                t = simple_type(sub["properties"].get(j) or {})
                if t in WRONG:
                    m = copy.deepcopy(value)
                    m[k][j] = WRONG[t]
                    out.append((f"nested_wrong_type:{k}.{j}", m))
    # DEVIATION (README): appended after the pre-registered strategies, so they are reached only
    # when those yield fewer than 10 library-rejected mutants for a tool (list_windows in the pilot
    # dry run): the first object item of each present array property.
    for k in sorted(value):
        items = (props.get(k) or {}).get("items") or {}
        arr = value.get(k)
        if isinstance(arr, list) and arr and isinstance(arr[0], dict) and isinstance(items.get("properties"), dict):
            for j in [x for x in (items.get("required") or []) if x in arr[0]]:
                m = copy.deepcopy(value)
                del m[k][0][j]
                out.append((f"array_item_drop_required:{k}[0].{j}", m))
            for j in sorted(arr[0]):
                t = simple_type(items["properties"].get(j) or {})
                if t in WRONG:
                    m = copy.deepcopy(value)
                    m[k][0][j] = WRONG[t]
                    out.append((f"array_item_wrong_type:{k}[0].{j}", m))
    return out


async def outcome(fn, session: Any, tool: str, value: Any) -> tuple[bool, str]:  # noqa: ANN001
    from mcp import types

    result = types.CallToolResult(content=[], structuredContent=value, isError=False)
    try:
        await fn(session, tool, result)
        return True, ""
    except Exception as exc:  # noqa: BLE001 - both paths raise RuntimeError on rejection
        return False, f"{type(exc).__name__}: {str(exc)[:240]}"


def read_corpus(raw: Path) -> list[dict[str, Any]]:
    for name in ("hc-corpus.jsonl.gz", "hc-corpus.jsonl"):
        p = raw / name
        if p.exists():
            opener = gzip.open if name.endswith(".gz") else open
            with opener(p, "rt", encoding="utf-8") as stream:
                return [json.loads(x) for x in stream if x.strip()]
    return []


async def run(args: argparse.Namespace) -> dict[str, Any]:
    sys.path.insert(0, str(HERE / "harness"))
    sys.path.insert(0, str(Path(args.wt).resolve() / "libs/cua-driver/examples/jev-use/python"))
    from mcp import ClientSession

    import n03_harness

    cls = n03_harness.make_session_class(ClientSession)
    raws = [Path(args.raw_root) / label for label in args.labels]
    schemas: dict[str, Any] = {}
    corpus: list[dict[str, Any]] = []
    for raw in raws:
        p = raw / "output-schemas.json"
        if p.exists() and not schemas:
            schemas = json.loads(p.read_text(encoding="utf-8"))
        corpus += read_corpus(raw)

    def new_session(hcl: bool) -> Any:
        s = object.__new__(cls)
        s._tool_output_schemas = dict(schemas)
        s.stamps = n03_harness.Stamps()
        s.hcl = hcl
        s.lazy = {}
        s.compiles = []
        s.equiv_log = None
        return s

    ref_session = new_session(False)
    lazy_session = new_session(True)  # one lazy cache for the whole control: compile at first use

    async def reference(sess: Any, tool: str, result: Any) -> None:
        await ClientSession._validate_tool_result(sess, tool, result)

    async def candidate(sess: Any, tool: str, result: Any) -> None:
        await cls._validate_tool_result(sess, tool, result)

    rows: list[dict[str, Any]] = []
    per_tool: dict[str, Any] = {}
    for tool in TOOLS:
        items = [x for x in corpus if x["tool"] == tool]
        seen: set[str] = set()
        kept: list[tuple[str, Any, str]] = []
        tried = 0
        for item in items:
            value = item["structuredContent"]
            ref_ok, ref_msg = await outcome(reference, ref_session, tool, value)
            cand_ok, cand_msg = await outcome(candidate, lazy_session, tool, value)
            rows.append({"tool": tool, "case": "real", "mutation": "none", "trial": item["trial"],
                         "reference_accepts": ref_ok, "lazy_accepts": cand_ok, "agree": ref_ok == cand_ok,
                         "same_message": ref_msg == cand_msg})
            if schemas.get(tool) is None or not isinstance(value, dict):
                continue
            for name, m in candidates(value, schemas[tool]):
                if len(kept) >= PER_TOOL:
                    break
                key = json.dumps(m, sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                tried += 1
                ok, msg = await outcome(reference, ref_session, tool, m)
                if not ok:
                    kept.append((name, m, item["trial"]))
        for name, m, trial in kept:
            ref_ok, ref_msg = await outcome(reference, ref_session, tool, m)
            cand_ok, cand_msg = await outcome(candidate, lazy_session, tool, m)
            rows.append({"tool": tool, "case": "invalid", "mutation": name, "trial": trial,
                         "reference_accepts": ref_ok, "lazy_accepts": cand_ok, "agree": ref_ok == cand_ok,
                         "same_message": ref_msg == cand_msg, "reference_error": ref_msg[:200]})
        inv = [x for x in rows if x["tool"] == tool and x["case"] == "invalid"]
        real = [x for x in rows if x["tool"] == tool and x["case"] == "real"]
        per_tool[tool] = {"real": len(real), "real_accepted_by_both": sum(1 for x in real if x["reference_accepts"] and x["lazy_accepts"]),
                          "invalid": len(inv), "candidates_tried": tried,
                          "invalid_rejected_by_both": sum(1 for x in inv if not x["reference_accepts"] and not x["lazy_accepts"]),
                          "same_message": sum(1 for x in inv + real if x["same_message"]),
                          "mutation_kinds": sorted({x["mutation"].split(":")[0] for x in inv})}
    ok = all(v["invalid"] == PER_TOOL and v["invalid_rejected_by_both"] == PER_TOOL and v["real"] > 0
             and v["real_accepted_by_both"] == v["real"] and v["same_message"] == v["invalid"] + v["real"]
             for v in per_tool.values())
    summary = {"pass": ok, "per_tool": per_tool, "rows": len(rows), "agree": sum(1 for x in rows if x["agree"]),
               "lazy_compiles": [c["tool"] for c in lazy_session.compiles], "labels": args.labels}
    return {"schema": "n03.hc_control.v1", "summary": summary, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt", required=True)
    ap.add_argument("--labels", nargs="+", default=["n03a2-a1", "n03a2-a2"])
    ap.add_argument("--out", default=str(HERE / "hc-control.json"))
    ap.add_argument("--raw-root", default=str(HERE / "raw" / "runs"))
    args = ap.parse_args()
    result = asyncio.run(run(args))
    Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
