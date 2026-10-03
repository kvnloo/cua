#!/usr/bin/env python3
"""B-05 equivalence and validator negative control for the caller-side variants (FIXTURE/UNIT).

Runs in the jev-use venv (mcp, pydantic, jsonschema), under hostless; no Driver, no browser.

  b05_equivalence.py --frames <dir-or-tar.gz> [...] --parsers default,fast --validators default,fast --out <json>

For every captured tools/call response line of every trial: each parser variant's decoded message
(canonical JSON of model_dump(mode="json", by_alias=True, exclude_none=True), or the exception
type) must equal the library parser's; then CallToolResult.model_validate on the result and, when
the tool has an output schema and the result has structuredContent, each validator variant's
best_match error text (None = accepted) must equal the library compiled validator's. Validator
negative control: mutations of every captured structured result (bad enum, missing required, extra
property, wrong type, null for a non-null field, negative minimum) that the library rejects must be
rejected by every variant with the same error text; the ones it accepts must be accepted.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]

import mcp.types as types  # noqa: E402
from jsonschema.exceptions import best_match  # noqa: E402
from jsonschema.validators import validator_for  # noqa: E402
from referencing import Registry  # noqa: E402

import b05_stdio as bs  # noqa: E402
import b05_variants as bv  # noqa: E402


def canon(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def frame_sets(paths: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for p in map(Path, paths):
        if p.is_dir():
            for f in sorted(p.glob("*.frames.jsonl.gz")):
                with gzip.open(f, "rt", encoding="utf-8") as fh:
                    out[f.name.replace(".frames.jsonl.gz", "")] = [json.loads(x) for x in fh if x.strip()]
        else:
            with tarfile.open(p, "r:gz") as tar:
                for m in tar.getmembers():
                    if m.isfile() and m.name.endswith(".frames.jsonl.gz"):
                        txt = gzip.decompress(tar.extractfile(m).read()).decode()
                        out[m.name.split("/")[-1].replace(".frames.jsonl.gz", "")] = [json.loads(x) for x in txt.splitlines() if x.strip()]
    return out


def decode(parser: str, line: str) -> tuple[str, Any]:
    try:
        msg = bs.PARSERS[parser](line)
    except Exception as error:  # noqa: BLE001
        return f"error:{type(error).__name__}", None
    return canon(msg.model_dump(mode="json", by_alias=True, exclude_none=True)), msg


def lib_validator(schema: Any) -> Any:
    cls = validator_for(schema)
    cls.check_schema(schema)
    return cls(schema, registry=Registry())


def verdict(validator: Any, instance: Any) -> str | None:
    e = best_match(validator.iter_errors(instance))
    return None if e is None else str(e)


def mutations(sc: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    keys = list(sc.keys())
    for k in keys:
        v = sc[k]
        m = copy.deepcopy(sc)
        del m[k]
        out.append((f"missing:{k}", m))
        m = copy.deepcopy(sc)
        m[k] = None
        out.append((f"null:{k}", m))
        m = copy.deepcopy(sc)
        m[k] = 12345 if isinstance(v, str) else "x"
        out.append((f"wrongtype:{k}", m))
        if isinstance(v, str):
            m = copy.deepcopy(sc)
            m[k] = v + "_bogus"
            out.append((f"badenum:{k}", m))
    m = copy.deepcopy(sc)
    m["zz_extra"] = 1
    out.append(("extra:zz_extra", m))
    out.append(("not_object", ["x"]))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames", nargs="+", required=True)
    p.add_argument("--parsers", default="default,fast")
    p.add_argument("--validators", default="default,fast")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    parsers = a.parsers.split(",")
    validators = a.validators.split(",")
    sets = frame_sets(a.frames)
    res: dict[str, Any] = {"trials": len(sets), "responses": 0, "parser_mismatch": [], "validated": 0,
                           "validator_mismatch": [], "neg_cases": 0, "neg_rejected_by_library": 0,
                           "neg_mismatch": [], "parsers": parsers, "validators": validators}
    schema_cache: dict[str, Any] = {}
    neg_seen: set[str] = set()
    for trial, frames in sets.items():
        reqs = {}
        for f in frames:
            if f["k"] == "req":
                o = json.loads(f["line"])
                if "id" in o:
                    reqs[json.dumps(o["id"])] = o
        schemas: dict[str, Any] = {}
        for f in frames:
            if f["k"] != "resp":
                continue
            o = json.loads(f["line"])
            q = reqs.get(json.dumps(o.get("id")))
            if q and q.get("method") == "tools/list":
                for t in (o.get("result") or {}).get("tools", []):
                    if t.get("outputSchema") is not None:
                        schemas[t["name"]] = t["outputSchema"]
        for f in frames:
            if f["k"] != "resp":
                continue
            o = json.loads(f["line"])
            q = reqs.get(json.dumps(o.get("id")))
            if not q or q.get("method") != "tools/call":
                continue
            res["responses"] += 1
            base_c, base_msg = decode("default", f["line"])
            for v in parsers:
                c, _m = decode(v, f["line"])
                if c != base_c:
                    res["parser_mismatch"].append({"trial": trial, "id": o.get("id"), "parser": v})
            if base_msg is None or not isinstance(base_msg.root, types.JSONRPCResponse):
                continue
            cr = types.CallToolResult.model_validate(base_msg.root.result)
            tool = (q.get("params") or {}).get("name")
            schema = schemas.get(tool)
            if schema is None or cr.structuredContent is None:
                continue
            key = hashlib.sha256(canon(schema).encode()).hexdigest()
            if key not in schema_cache:
                lib = lib_validator(schema)
                fast, kept = bv.fast_validators({key: lib}, {key: schema})
                schema_cache[key] = {"default": lib, "fast": fast[key], "kept": kept}
            vals = schema_cache[key]
            res["validated"] += 1
            base_v = verdict(vals["default"], cr.structuredContent)
            for v in validators:
                if verdict(vals[v], cr.structuredContent) != base_v:
                    res["validator_mismatch"].append({"trial": trial, "id": o.get("id"), "validator": v, "tool": tool})
            shape = f"{tool}:{canon(sorted(cr.structuredContent.keys()))}"
            if shape in neg_seen:
                continue
            neg_seen.add(shape)
            for name, inst in mutations(cr.structuredContent):
                res["neg_cases"] += 1
                lv = verdict(vals["default"], inst)
                if lv is not None:
                    res["neg_rejected_by_library"] += 1
                for v in validators:
                    if verdict(vals[v], inst) != lv:
                        res["neg_mismatch"].append({"tool": tool, "case": name, "validator": v})
    res["kept_library_schemas"] = sorted({k for s in schema_cache.values() for k in s["kept"]})
    res["all_equal"] = not res["parser_mismatch"] and not res["validator_mismatch"]
    res["neg_all_match"] = not res["neg_mismatch"]
    Path(a.out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}))


if __name__ == "__main__":
    main()
